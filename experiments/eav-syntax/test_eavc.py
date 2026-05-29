"""Tests for the EAV-Steps compiler (eavc.py).

Project rule (todos.md scope rule): no item is "done" without a test that would
fail under a no-op lowering. eavc lowers EAV directly to LLVM IR via llvmlite;
the end-to-end tests JIT-run the program (via `eavc.py run`) and assert on
stdout + exit code, and the IR tests assert on generated instructions — both go
red under a stubbed/no-op code generator.

Run:  python -m pytest experiments/eav-syntax/test_eavc.py -q
"""

import os
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import eavc  # noqa: E402

EXAMPLES = os.path.join(HERE, "examples")
INVALID_CORPUS = os.path.join(HERE, "invalid_corpus")
SIGS = os.path.join(HERE, "sigs")
STD = os.path.join(HERE, "std")
APPS = os.path.join(HERE, "apps")
# The untouched v0.1 SemanticScript apps at the repo root — the porting source of
# record and the parity baseline (X-047). The EAV ports under APPS must not mutate them.
V1_APPS = os.path.normpath(os.path.join(HERE, "..", "..", "apps"))


def _app_program(app, *stdlibs):
    """Compose an app project (build.sem project + src/ modules, via load_project)
    with the stdlib modules it imports (eavc has no cross-file import resolution,
    so tests assemble what an importer would)."""
    parts = [open(os.path.join(STD, s), encoding="utf-8").read() for s in stdlibs]
    parts.append(eavc.load_project(os.path.join(APPS, app)))
    return "\n".join(parts)


def _have_c_compiler():
    return eavc._find_c_compiler() is not None


# A `main` that drives the standard.sqlite surface through a full round-trip.
# eavc has no cross-file import resolution, so the parity test composes the
# stdlib module with this main (what an importer would assemble).
_SQLITE_ROUNDTRIP_MAIN = """
SqliteRoundTrip is project
SqliteRoundTrip module appSqliteRoundTrip
SqliteRoundTrip target console
SqliteRoundTrip entry main

appSqliteRoundTrip is module
appSqliteRoundTrip path examples.sqliteRoundTrip
appSqliteRoundTrip exports main
appSqliteRoundTrip purpose "Exercise the standard.sqlite round-trip end to end"
appSqliteRoundTrip invariant "Prints the text column read back from the inserted row"

ExitCode is alias
ExitCode for Int32

main is operation
main out ExitCode
main async no
main purpose "Open in-memory, create+insert, prepare+step, read the text column, print it"
main invariant "Prints the name inserted into the row"
main let createSql immutable String "CREATE TABLE t(id INTEGER, name TEXT)"
main let insertSql immutable String "INSERT INTO t VALUES(7, 'eav')"
main let selectSql immutable String "SELECT id, name FROM t"
main let nameColumn immutable Int32 1
main let okCode immutable ExitCode 0
main do dbOpen
main do createTbl
main do insertRow
main do prepareSelect
main do stepRow
main do readName
main do showName
main do finalizeSelect
main do closeDb
main return okCode

dbOpen is call
dbOpen in main
dbOpen invokes openInMemory
dbOpen out database SqliteDatabase

createTbl is call
createTbl in main
createTbl invokes exec
createTbl arg database SqliteDatabase database
createTbl arg sql String createSql
createTbl discards "create-table status"

insertRow is call
insertRow in main
insertRow invokes exec
insertRow arg database SqliteDatabase database
insertRow arg sql String insertSql
insertRow discards "insert status"

prepareSelect is call
prepareSelect in main
prepareSelect invokes prepareStatement
prepareSelect arg database SqliteDatabase database
prepareSelect arg sql String selectSql
prepareSelect out selectStatement SqliteStatement

stepRow is call
stepRow in main
stepRow invokes stepStatement
stepRow arg statement SqliteStatement selectStatement
stepRow discards "step outcome (row expected)"

readName is call
readName in main
readName invokes columnText
readName arg statement SqliteStatement selectStatement
readName arg columnIndex Int32 nameColumn
readName out nameText SqliteText

showName is call
showName in main
showName invokes console.writeLine
showName arg text String nameText

finalizeSelect is call
finalizeSelect in main
finalizeSelect invokes finalizeStatement
finalizeSelect arg statement SqliteStatement selectStatement
finalizeSelect discards "finalize status"

closeDb is call
closeDb in main
closeDb invokes closeDatabase
closeDb arg database SqliteDatabase database
closeDb discards "close status"
"""


def _corpus_files():
    import glob
    return sorted(glob.glob(os.path.join(INVALID_CORPUS, "*.sem")))


@pytest.mark.parametrize("path", _corpus_files())
def test_invalid_corpus_all_reject(path):
    # X-006 / §29 #1: every invalid-example fixture is rejected at parse time.
    src = open(path, encoding="utf-8").read()
    with pytest.raises(eavc.EavError):
        eavc.parse(src)


def test_invalid_corpus_is_populated():
    assert len(_corpus_files()) >= 15


MANIFESTS = os.path.join(HERE, "manifests")


def test_module_path_and_internal_visibility():
    # WS3-032: submodule path = root + reldir; internal/ leak rejected.
    assert eavc.module_path_for("acme", "app/taskWeb") == "acme.app.taskWeb"
    assert eavc.internal_import_allowed("acme.app.handlers", "acme.app.internal.db")
    assert eavc.internal_import_allowed("acme.app", "acme.app.internal.db")
    assert not eavc.internal_import_allowed("other.mod", "acme.app.internal.db")
    assert eavc.internal_import_allowed("anything", "acme.app.public")  # no internal seg


def test_mod_tidy_reproducible_and_valid_lock():
    # WS3-035: tidy generates a valid, reproducible lock from the manifest.
    build = eavc.parse(open(os.path.join(MANIFESTS, "build.sem"), encoding="utf-8").read())
    lock1 = eavc.mod_tidy(build)
    lock2 = eavc.mod_tidy(build)
    assert lock1 == lock2                       # reproducible
    lockprog = eavc.parse(lock1)                # valid EAV
    proj = lockprog.entities["TaskApp"]
    assert len(proj.facts("resolved")) == 2
    assert all(eavc.is_sha256_digest(r.payload[-1]) for r in proj.facts("resolved"))
    # the generated lock is consistent with the manifest allowlist
    eavc.verify_supply_chain(build, lockprog)


def test_supply_chain_allowlist():
    # WS3-036: a dep effect not in allowEffect is refused.
    build = eavc.parse(
        "P is project\nP allowEffect read database\nP allowEffect write console.stdout\n"
    )
    ok_lock = eavc.parse("P is project\nP effectSurface read database\n")
    eavc.verify_supply_chain(build, ok_lock)  # ok
    bad_lock = eavc.parse("P is project\nP effectSurface connect socket\n")
    with pytest.raises(eavc.EavError) as exc:
        eavc.verify_supply_chain(build, bad_lock)
    assert exc.value.code == "SS2805"


def test_supply_chain_diff_flags_new_effect():
    # X-081 / §28.5: a dependency newly requesting an effect is a sem-diff finding.
    old_lock = eavc.parse("P is project\nP effectSurface read database\n")
    new_lock = eavc.parse(
        "P is project\nP effectSurface read database\nP effectSurface connect socket\n")
    assert eavc.supply_chain_diff(old_lock, new_lock) == [("connect", "socket")]
    # no spurious finding when nothing changed
    assert eavc.supply_chain_diff(old_lock, old_lock) == []


def test_supply_chain_transitive_escalation_rejected():
    # X-081: no transitive capability escalation — a transitive dep's effect that
    # exceeds the root allowlist is fail-closed (the surface is the transitive
    # closure, so it is caught by verify_supply_chain / SS2805).
    build = eavc.parse("P is project\nP allowEffect read database\n")
    transitive_lock = eavc.parse(
        "P is project\nP effectSurface read database\nP effectSurface write filesystem\n")
    with pytest.raises(eavc.EavError) as exc:
        eavc.verify_supply_chain(build, transitive_lock)
    assert exc.value.code == "SS2805"


def test_supply_chain_manifest_goldens_consistent():
    build = eavc.parse(open(os.path.join(MANIFESTS, "build.sem"), encoding="utf-8").read())
    lock = eavc.parse(open(os.path.join(MANIFESTS, "build.sem.lock"), encoding="utf-8").read())
    eavc.verify_supply_chain(build, lock)  # the goldens are consistent


def test_console_entry_with_in_params_flagged():
    # WS3-039 / README §11: console entry takes no `in` parameters.
    prog = eavc.parse(
        "P is project\nP module m\nP target console\nP entry main\nm is module\nm path a.b\n"
        "main is operation\nmain in extra Int64\nmain out ExitCode\n"
    )
    assert "SS1190" in {d.code for d in eavc.lint(prog)}


def test_console_entry_wrong_return_flagged():
    prog = eavc.parse(
        "P is project\nP module m\nP target console\nP entry main\nm is module\nm path a.b\n"
        "main is operation\nmain out String\n"
    )
    assert "SS1191" in {d.code for d in eavc.lint(prog)}


def test_export_c_duplicate_symbol_rejected():
    # WS3-054 / README §30.4.2: export symbols must be unique C identifiers.
    src = (
        "a is operation\na out Int64\na export c shared_sym\n"
        "b is operation\nb out Int64\nb export c shared_sym\n"
    )
    codes = {d.code for d in eavc.lint(eavc.parse(src))}
    assert "SS3043" in codes


def test_export_c_bad_identifier_rejected():
    src = "a is operation\na out Int64\na export c bad-name\n"
    # `bad-name` won't even tokenize cleanly as one token? It will: bad-name is one bare token.
    codes = {d.code for d in eavc.lint(eavc.parse(src))}
    assert "SS3042" in codes


def test_export_c_valid_unique_ok():
    src = (
        "a is operation\na out Int64\na export c alpha_sym\n"
        "b is operation\nb out Int64\nb export c beta_sym\n"
    )
    codes = {d.code for d in eavc.lint(eavc.parse(src))}
    assert "SS3043" not in codes and "SS3042" not in codes


def test_semsig_catalogs_load_and_doc():
    # WS3-023: every .semsig catalog loads and `docs` lists its API surface.
    import glob
    sig_files = sorted(glob.glob(os.path.join(SIGS, "*.semsig")))
    assert len(sig_files) >= 3
    for path in sig_files:
        prog = eavc.load_semsig(open(path, encoding="utf-8").read())
        api = eavc.docs(prog)
        assert api, f"{path} produced no docs"
    # the console catalog documents writeLine with its throws clause
    console = eavc.load_semsig(open(os.path.join(SIGS, "standard.console.semsig"),
                                    encoding="utf-8").read())
    lines = eavc.docs(console)
    assert any("console.writeLine(String)" in l and "throws ConsoleWriteError" in l
               for l in lines)
    # the http catalog documents the §34-migration surface (route/serve/callNext)
    http = eavc.load_semsig(open(os.path.join(SIGS, "standard.http.semsig"),
                                 encoding="utf-8").read())
    http_lines = eavc.docs(http)
    assert any(l.startswith("http.route(") for l in http_lines)
    assert any("http.serve(" in l and "throws HttpError" in l for l in http_lines)
    assert any(l.startswith("http.callNext(") for l in http_lines)


def test_semsig_loads_and_indexes_targets():
    # WS3-050/051/052: load a .semsig, validate header, index intrinsic targets.
    prog = eavc.load_semsig(open(os.path.join(SIGS, "standard.sqlite.semsig"),
                                 encoding="utf-8").read())
    targets = eavc.semsig_targets(prog)
    assert "sqlite.openDatabase" in targets
    assert targets["sqlite.openDatabase"].fact("owns").payload == ["SqliteDatabase"]


def test_semsig_unknown_version_rejected():
    with pytest.raises(eavc.EavError) as exc:
        eavc.load_semsig('s is semsig\ns version "9.9"\ns describes x.y\n')
    assert exc.value.code == "SS2601"


def test_semsig_resolution_first_wins():
    a = eavc.parse("s is semsig\ns version \"1.0\"\ni is intrinsic\ni target foo.bar\n")
    b = eavc.parse("s is semsig\ns version \"1.0\"\nj is intrinsic\nj target foo.bar\n")
    assert eavc.resolve_semsig("foo.bar", [a, b]) is a
    assert eavc.resolve_semsig("nope.thing", [a, b]) is None


def test_app_source_intrinsic_body_warns():
    # WS3-052 / §17 #50: a primitive body in app source is a lint warning.
    prog = eavc.parse(
        "doThing is operation\ndoThing out Int64\n"
        "doThing body intrinsic arithmetic.addInt64\n"
    )
    codes = {d.code for d in eavc.lint(prog)}
    assert "SS5000" in codes


def test_mvs_selects_highest():
    # WS3-033: minimal version selection picks the highest required version.
    reqs = [("a", "v1.2.0"), ("a", "v1.3.0"), ("a", "v1.2.9"), ("b", "v2.0.0")]
    assert eavc.mvs_select(reqs) == {"a": "v1.3.0", "b": "v2.0.0"}


def test_mvs_release_beats_prerelease():
    assert eavc.mvs_select([("a", "v1.0.0-rc.1"), ("a", "v1.0.0")]) == {"a": "v1.0.0"}


def test_sha256_digest_verify_and_mismatch():
    # WS3-034: content-addressed integrity; tampered content rejects.
    data = b"dependency bytes"
    eavc.verify_digest(data, eavc.sha256_hex(data))  # ok
    with pytest.raises(eavc.EavError) as exc:
        eavc.verify_digest(b"tampered", eavc.sha256_hex(data))
    assert exc.value.code == "SS2804"


def test_configure_op_excluded_from_runtime_build():
    # WS3-038: a configure op is not lowered into the runtime module.
    src = (
        "P is project\nP module m\nP target console\nP entry main\nP configure setup\n"
        "m is module\nm path a.b\n"
        "setup is operation\nsetup out ExitCode\n"
        "setup let s immutable ExitCode 0\nsetup return s\n"
        "main is operation\nmain out ExitCode\n"
        "main let okCode immutable ExitCode 0\nmain return okCode\n"
    )
    ir_text = _ir_for_source(src)
    assert '@"main"' in ir_text
    assert '@"setup"' not in ir_text  # build-time, excluded


def test_configure_runtime_effect_rejected():
    # WS3-005: a configure op with a runtime effect is rejected.
    src = (
        "P is project\nP module m\nP target console\nP entry main\nP configure setup\n"
        "m is module\nm path a.b\n"
        "setup is operation\nsetup out ExitCode\nsetup effect write console.stdout\n"
        "main is operation\nmain out ExitCode\n"
    )
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(src)
    assert exc.value.code == "SS3002"


def test_platform_targetruntime_validated():
    # WS3-040: a platform targetRuntime must be native or wasm.
    eavc.parse("p is platform\np targetRuntime native\n")  # ok
    eavc.parse("p is platform\np targetRuntime wasm\n")     # ok
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse("p is platform\np targetRuntime jvm\n")
    assert exc.value.code == "SS0740"


def test_build_plan_builder_merge_by_name():
    # WS3-021: standard.build BuildPlan builder; withTarget merges by name (replace).
    plan = eavc.build_empty_plan()
    assert plan == {"targets": {}, "constants": {}}
    plan = eavc.build_with_target(plan, "app", "console")
    plan = eavc.build_with_constant(plan, "release", "true")
    plan = eavc.build_with_target(plan, "app", "wasm")  # same name -> replace
    assert plan["targets"] == {"app": "wasm"}
    assert plan["constants"] == {"release": "true"}


def test_native_link_merge_and_dedup():
    # WS3-037: per-platform output + ordered/deduped native-link flags.
    prog = eavc.parse(open(os.path.join(MANIFESTS, "build.sem"), encoding="utf-8").read())
    merged = eavc.merge_native_links(prog, "linuxX64")
    assert merged["output"] == "bin/taskapp"
    assert merged["libraries"] == ["sqlite3"]
    assert merged["linkFlags"] == ["-lpthread"]


def test_native_link_dedup_project_and_platform():
    src = (
        'A is project\nA nativeLibrary "sqlite3"\nA nativeLinkFlag "-lm"\n'
        'p is platform\np os linux\np arch x64\np output "bin/x"\n'
        'p nativeLibrary "sqlite3"\np nativeLinkFlag "-lpthread"\n'  # sqlite3 dup
    )
    merged = eavc.merge_native_links(eavc.parse(src), "p")
    assert merged["libraries"] == ["sqlite3"]                  # deduped
    assert merged["linkFlags"] == ["-lm", "-lpthread"]          # order preserved


def test_html_holes_extracted_and_url_flagged():
    # WS3-018: {{name}} / {{rec.field}} extraction; URL-attribute holes flagged.
    holes = eavc.html_holes('<a href="{{link}}">{{label}}</a> {{user.name}}')
    by = dict(holes)
    assert by["link"] is True       # inside href -> URL hole
    assert by["label"] is False
    assert "user.name" in by


def test_html_legacy_single_brace_rejected():
    # README §16: legacy single-brace holes are a breaking error.
    with pytest.raises(eavc.EavError) as exc:
        eavc.html_holes("<h1>Hello {name}</h1>")
    assert exc.value.code == "SS1633"


def test_html_render_template_well_formed_parses():
    prog = eavc.parse(open(os.path.join(MANIFESTS, "page.sem"), encoding="utf-8").read())
    assert prog.entities["greetingPage"].kind == "htmlTemplate"


def test_html_render_url_hole_must_be_htmlsafeurl():
    # README §17 #34: a URL-attribute hole filled with String is rejected.
    src = (
        "p is htmlTemplate\np body html\n    <a href=\"{{link}}\">x</a>\n"
        "r is call\nr in show\nr invokes html.render\n"
        "r arg template HtmlTemplate p\nr arg link String someUrl\nr out frag HtmlFragment\n"
    )
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(src)
    assert exc.value.code == "SS1634"


def test_html_render_args_must_match_holes():
    src = (
        "p is htmlTemplate\np body html\n    <h1>{{name}}</h1>\n"
        "r is call\nr in show\nr invokes html.render\n"
        "r arg template HtmlTemplate p\nr arg wrongHole String x\nr out frag HtmlFragment\n"
    )
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(src)
    assert exc.value.code == "SS1635"


def test_fallible_call_without_error_path_warns():
    # README §17 #35: a fallible call with no ifError warns (cleanup worker exempt).
    src = (
        "main is operation\nmain out ExitCode\n"
        'main let t immutable String "hi"\nmain do w\nmain return okCode\n'
        "main let okCode immutable ExitCode 0\n"
        "w is call\nw in main\nw invokes console.writeLine\nw arg text String t\n"
        "w catch e ConsoleWriteError\n"   # fallible, but no branch ifError w
    )
    assert "SS3501" in {d.code for d in eavc.lint(eavc.parse(src))}


def test_build_sem_full_grammar_parses():
    # WS3-030: the full build.sem manifest grammar parses.
    prog = eavc.parse(open(os.path.join(MANIFESTS, "build.sem"), encoding="utf-8").read())
    proj = prog.entities["TaskApp"]
    assert [r.payload for r in proj.facts("target")] == [["console"], ["wasm"]]
    assert proj.fact("languageVersion").payload == ['"1.0"']
    assert len(proj.facts("require")) == 2
    assert proj.fact("require").payload == ["github.com/ss-lang/sqlite", "v2.1.0"]
    assert prog.entities["linuxX64"].kind == "platform"


def test_build_sem_lock_parses_with_lock_predicates():
    # WS3-031: the generated lock uses resolved/toolchainResolved/effectSurface.
    prog = eavc.parse(open(os.path.join(MANIFESTS, "build.sem.lock"), encoding="utf-8").read())
    proj = prog.entities["TaskApp"]
    assert proj.fact("toolchainResolved").payload == ['"sem1.0"']
    assert len(proj.facts("resolved")) == 2
    # sha256 digest body is recognized as a manifest token
    res = proj.fact("resolved")
    assert eavc.is_sha256_digest(res.payload[-1])
    assert len(proj.facts("effectSurface")) == 2


def _example_files():
    import glob
    return sorted(glob.glob(os.path.join(EXAMPLES, "*.sem")))


@pytest.mark.parametrize("path", _example_files())
def test_conformance_matrix_all_lanes(path):
    # X-001: every example golden passes parser + lowering + formatter(idempotent)
    # + linter (no error-severity) lanes together.
    import llvmlite.binding as llvm
    eavc._ensure_native_init()
    src = open(path, encoding="utf-8").read()
    prog = eavc.parse(src)                                   # parser lane
    ir_text = str(eavc.lower_to_llvm(prog))                  # lowering lane
    llvm.parse_assembly(ir_text).verify()                    # IR verifies
    once = eavc.format_program(prog)                         # formatter lane
    assert eavc.format_program(eavc.parse(once)) == once     # idempotent
    diags = eavc.lint(prog)                                  # linter lane
    assert not any(d.severity == "error" for d in diags), [d.render() for d in diags]


_COMPACT_HELLO = """\
HelloWorld is project
HelloWorld module examplesHello
HelloWorld target console
HelloWorld entry main

examplesHello is module
examplesHello path examples.hello
examplesHello exports main
examplesHello purpose "Print a greeting"
examplesHello invariant "Writes the greeting once"

ExitCode is alias
ExitCode for Int32

stdoutWriter is capability
stdoutWriter grants write console.stdout
stdoutWriter purpose "Allow controlled stdout writes"

operation main
out ExitCode
effect write console.stdout using stdoutWriter
memory heap no
async no
purpose "Print hi and exit zero"
invariant "Writes hi"
let hi immutable String "hi"
let okCode immutable ExitCode 0
do writeHi
return okCode

call writeHi console.writeLine
arg text String hi
"""


def test_captured_output_replay_deterministic_and_side_effect_free():
    # WS3-004 / README §30.1.1: a `mode capturedOutputReplay` program records a
    # transcript, is deterministic across record runs, and replays it without
    # re-performing the effect. The transcript holds the program's *real* output,
    # so a no-op lowering (empty transcript) fails this test.
    src = open(os.path.join(EXAMPLES, "replay_demo.sem"), encoding="utf-8").read()
    result = eavc.captured_output_replay(src)
    assert result["mode"] == "capturedOutputReplay"
    assert result["transcript"] == ["replay me"]
    assert result["exitCode"] == 0
    assert result["deterministic"] is True
    assert result["sideEffectFree"] is True
    # replay reproduces the recorded transcript exactly
    assert result["replayStdout"].strip() == "replay me"


def test_captured_output_replay_requires_mode():
    # The harness refuses a program that did not opt into the determinism mode.
    src = open(os.path.join(EXAMPLES, "hello_world.sem"), encoding="utf-8").read()
    with pytest.raises(eavc.EavError):
        eavc.captured_output_replay(src)


def test_compact_is_not_valid_raw_eav():
    # The strict EAV parser rejects compact bare rows (no subject) — proving the
    # compact expander does real work and is not a no-op (WS4-004).
    with pytest.raises(eavc.EavError):
        eavc.parse(_COMPACT_HELLO)


def test_compact_expands_parses_and_runs(tmp_path):
    # Compact -> EAV expansion parses and JIT-runs to the expected output.
    prog = eavc.parse_compact(_COMPACT_HELLO)
    assert prog.entities["writeHi"].kind == "call"
    assert prog.entities["writeHi"].fact("invokes").payload == ["console.writeLine"]
    assert prog.entities["writeHi"].fact("in").payload == ["main"]
    # `effect … using` expanded into an effect row + a uses row on main
    assert [r.payload for r in prog.entities["main"].facts("effect")] == [["write", "console.stdout"]]
    assert prog.entities["main"].fact("uses").payload == ["stdoutWriter"]
    src_file = tmp_path / "compact_hello.sem"
    eav_text, _ = eavc.expand_compact_to_eav(_COMPACT_HELLO)
    src_file.write_bytes(eav_text.encode("utf-8"))
    out = subprocess.run(
        [sys.executable, os.path.join(HERE, "eavc.py"), "run", str(src_file)],
        capture_output=True, text=True,
    )
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "hi"


def test_compact_eav_roundtrip_semantics_preserved():
    # compact -> EAV -> compact -> EAV preserves the entity set and per-entity
    # row counts (gate-0 round-trip, WS4-004).
    a = eavc.parse_compact(_COMPACT_HELLO)
    b = eavc.parse_compact(eavc.format_compact(a))
    assert set(a.order) == set(b.order)
    assert {n: len(a.entities[n].rows) for n in a.order} == {
        n: len(b.entities[n].rows) for n in b.order
    }


def test_fmt_surface_eav_idempotent_on_canonical():
    # parse_compact is idempotent on already-canonical EAV: formatting a golden
    # through the compact front end equals formatting it directly.
    src = open(os.path.join(EXAMPLES, "add_two.sem"), encoding="utf-8").read()
    assert eavc.format_program(eavc.parse_compact(src)) == eavc.format_program(eavc.parse(src))


def test_compact_diagnostic_maps_to_compact_line():
    # WS2-004: a lint diagnostic on the canonical EAV maps back to the author's
    # original compact line through the expansion source map.
    compact = (
        "Demo is project\nDemo module demoMod\nDemo target console\nDemo entry main\n"
        "demoMod is module\ndemoMod path demo.mod\n"
        "demoMod exports main\ndemoMod exports needsInv\n"
        'demoMod purpose "p"\ndemoMod invariant "i"\n'
        "ExitCode is alias\nExitCode for Int32\n"
        "stdoutWriter is capability\nstdoutWriter grants write console.stdout\n"
        'stdoutWriter purpose "p"\n'
        "operation main\nout ExitCode\n"
        "effect write console.stdout using stdoutWriter\n"
        'purpose "p"\ninvariant "i"\n'
        'let hi immutable String "hi"\nlet okCode immutable ExitCode 0\n'
        "do writeHi\nreturn okCode\n"
        "call writeHi console.writeLine\narg text String hi\n"
        # second op, exported, missing invariant -> MD1012; appears AFTER the
        # call header (+2 lines) and effect-using (+1 line) expansions
        "operation needsInv\nout ExitCode\n"
        'purpose "p"\nlet okCode2 immutable ExitCode 0\nreturn okCode2\n'
    )
    compact_lines = compact.split("\n")
    mapped = [d for d in eavc.lint_compact(compact) if d.code == "MD1012"]
    assert mapped, "expected MD1012 (missing invariant) on needsInv"
    line = mapped[0].line
    assert compact_lines[line - 1].strip() == "operation needsInv"
    # the source map did real work: the canonical line differs from the compact line
    eav_text, _ = eavc.expand_compact_to_eav(compact)
    raw = [d for d in eavc.lint(eavc.parse(eav_text)) if d.code == "MD1012"][0]
    assert raw.line != line


def _ir_for(name: str) -> str:
    """Parse an example and return its generated LLVM IR as text."""
    program = eavc.parse(open(os.path.join(EXAMPLES, name), encoding="utf-8").read())
    return str(eavc.lower_to_llvm(program))


def _ir_for_source(src: str) -> str:
    return str(eavc.lower_to_llvm(eavc.parse(src)))


# --------------------------------------------------------------------------
# Diagnostic registry / explain (README ss17, ss29 #12)
# --------------------------------------------------------------------------


def test_query_dimensions():
    prog = eavc.parse(_ir_helper_program())
    assert eavc.query(prog, "calls") == ["s math.addInt64"]
    assert "addTwo" in " ".join(eavc.query(prog, "types")) or eavc.query(prog, "types") == []
    # effects: helper program has none declared
    assert eavc.query(prog, "effects") == []


def test_query_ownership_leaked():
    src = (
        "openDb is call\nopenDb in main\nopenDb invokes sqlite.openDatabase\n"
        "openDb out db Int64\nopenDb owns db\n"  # owns but no cleanedBy
    )
    leaked = eavc.query(eavc.parse(src), "ownership-leaked")
    assert any("openDb" in r for r in leaked)


@pytest.mark.parametrize("name", ["hello_world.sem", "add_two.sem", "countdown.sem",
                                   "factorial.sem", "record_demo.sem"])
def test_fmt_is_idempotent(name):
    # WS4-002: fmt(fmt(x)) == fmt(x).
    src = open(os.path.join(EXAMPLES, name), encoding="utf-8").read()
    once = eavc.format_program(eavc.parse(src))
    twice = eavc.format_program(eavc.parse(once))
    assert once == twice


def test_fmt_sugar_async_call_promotes_to_task():
    # WS4-003: `call ... async yes` promotes to `is task` on fmt (async dropped).
    src = "fetchThing is call\nfetchThing invokes net.fetch\nfetchThing async yes\n"
    out = eavc.format_program(eavc.parse(src))
    assert "fetchThing is task" in out
    assert "async" not in out
    assert eavc.format_program(eavc.parse(out)) == out  # idempotent


def test_fmt_sugar_branch_else_to_goto():
    # WS4-003: `branch else ... target L` canonicalizes to `goto L`.
    src = (
        "main is operation\nmain out ExitCode\n"
        "main let okCode immutable ExitCode 0\n"
        "main branch else target done\nmain at done return okCode\n"
    )
    out = eavc.format_program(eavc.parse(src))
    assert "main goto done" in out
    assert "branch else" not in out
    assert eavc.format_program(eavc.parse(out)) == out


def test_fmt_metadata_sorts_after_structural():
    # WS4-001 / README §22: metadata rows sort after structural rows.
    src = (
        "main is operation\n"
        'main purpose "p"\n'         # metadata declared before structural
        "main out ExitCode\n"
        "main effect write console.stdout\n"
    )
    out = eavc.format_program(eavc.parse(src))
    lines = out.splitlines()
    out_idx = lines.index("main out ExitCode")
    eff_idx = lines.index("main effect write console.stdout")
    pur_idx = next(i for i, l in enumerate(lines) if l.startswith("main purpose"))
    assert out_idx < pur_idx and eff_idx < pur_idx


def test_fmt_preserves_island_indentation():
    # WS4-005: an island body must not be de-indented.
    src = (
        "q is storage\nq scope module\nq type SqlText\nq mutability immutable\n"
        "q body sql\n    SELECT id, title\n    FROM tasks\n"
    )
    out = eavc.format_program(eavc.parse(src))
    assert "    SELECT id, title" in out
    assert "    FROM tasks" in out
    # idempotent over islands too
    assert eavc.format_program(eavc.parse(out)) == out


def test_fmt_output_still_runs():
    # Formatting must be semantics-preserving: the formatted golden still JITs.
    src = open(os.path.join(EXAMPLES, "add_two.sem"), encoding="utf-8").read()
    formatted = eavc.format_program(eavc.parse(src))
    prog = eavc.parse(formatted)
    ir_text = str(eavc.lower_to_llvm(prog))
    assert 'call i64 @"addTwoValues"' in ir_text


def test_trace_lists_steps_and_bindings():
    prog = eavc.parse(open(os.path.join(EXAMPLES, "add_two.sem"), encoding="utf-8").read())
    lines = eavc.trace(prog, "main")
    text = "\n".join(lines)
    assert "do answerCall -> answerValue" in text
    assert "do writeAnswer" in text
    assert "return successExitCode" in text
    # live binding set grows as bindings are introduced
    assert any("answerValue" in l and "live:" in l for l in lines)


def test_trace_defers_run_reverse():
    lines = eavc.trace(eavc.parse(_DEFER_TRACE_SRC), "main")
    assert any("defers run (reverse): ['cleanupB', 'cleanupA']" in l for l in lines)


_DEFER_TRACE_SRC = (
    "ownerA is call\nownerA in main\nownerA invokes x.o\nownerA out rA Int64\n"
    "ownerA owns rA\nownerA cleanedBy cleanupA\n"
    "ownerB is call\nownerB in main\nownerB invokes x.p\nownerB out rB Int64\n"
    "ownerB owns rB\nownerB cleanedBy cleanupB\n"
    "wA is call\nwA in main\nwA invokes x.a\n"
    "wB is call\nwB in main\nwB invokes x.b\n"
    "cleanupA is cleanup\ncleanupA in main\ncleanupA call wA\ncleanupA cleans rA\n"
    "cleanupB is cleanup\ncleanupB in main\ncleanupB call wB\ncleanupB cleans rB\n"
    "main is operation\nmain out ExitCode\nmain let okCode immutable ExitCode 0\n"
    "main do ownerA\nmain do ownerB\nmain defer cleanupA\nmain defer cleanupB\n"
    "main return okCode\n"
)


def test_normalize_preview_round_trip_preserved():
    src = open(os.path.join(EXAMPLES, "add_two.sem"), encoding="utf-8").read()
    p = eavc.normalize_preview(src)
    assert p["roundTripPreserved"] is True
    assert p["rowCount"] > 0
    # a metadata-before-structural source is reported as "changed"
    unsorted_src = (
        "main is operation\nmain purpose \"p\"\nmain out ExitCode\n"
    )
    assert eavc.normalize_preview(unsorted_src)["changed"] is True


def test_normalize_preview_already_canonical_unchanged():
    canonical = eavc.format_program(eavc.parse(eavc.scaffold("console-program")))
    assert eavc.normalize_preview(canonical)["changed"] is False


def test_verify_patch_ok_on_scaffold():
    report = eavc.verify_patch(eavc.scaffold("console-program"))
    assert report["ok"] is True
    assert report["parsed"] and report["lowerable"]
    assert report["lintErrors"] == []


def test_verify_patch_fails_on_parse_error():
    report = eavc.verify_patch("main do nowhere\n")  # first row not `is`
    assert report["ok"] is False
    assert report["parsed"] is False
    assert report["error"]


def test_verify_patch_fails_on_lint_error():
    # exported op missing purpose/invariant -> MD lint errors
    src = "m is module\nm path a.b\nm purpose \"x\"\nm invariant \"y\"\nm exports run\nrun is operation\nrun out Int64\n"
    report = eavc.verify_patch(src)
    assert report["ok"] is False
    assert report["lintErrors"]


def test_semantic_diff_detects_changes():
    old = eavc.parse(
        "a is operation\na out Int64\n"
        "b is operation\nb out Int64\nb effect write console.stdout\n"
    )
    new = eavc.parse(
        "a is operation\na out ExitCode\n"          # out changed
        "added is operation\nadded out Int64\n"     # b removed, added added
    )
    diff = eavc.semantic_diff(old, new)
    text = "\n".join(diff)
    assert "+ operation added" in text
    assert "- operation b" in text
    assert "~ a: out" in text


def test_describe_entity_summary():
    prog = eavc.parse(open(os.path.join(EXAMPLES, "add_two.sem"), encoding="utf-8").read())
    text = eavc.describe(prog, "addTwoValues")
    assert "addTwoValues : operation" in text
    assert "in leftValue Int64" in text
    assert "out Int64" in text
    assert "steps" in text


def test_describe_unknown_entity_errors():
    prog = eavc.parse(open(os.path.join(EXAMPLES, "add_two.sem"), encoding="utf-8").read())
    with pytest.raises(eavc.EavError):
        eavc.describe(prog, "nope")


def test_graph_calls_dot():
    ir = eavc.parse(open(os.path.join(EXAMPLES, "add_two.sem"), encoding="utf-8").read())
    dot = eavc.graph(ir, "calls", "dot")
    assert "digraph calls {" in dot
    assert '"main" -> "addTwoValues";' in dot


def test_graph_control_and_mermaid():
    prog = eavc.parse(open(os.path.join(EXAMPLES, "countdown.sem"), encoding="utf-8").read())
    control = eavc.graph(prog, "control", "dot")
    assert "loopHead" in control and "loopExit" in control
    mer = eavc.graph(prog, "calls", "mermaid")
    assert mer.startswith("graph TD")


@pytest.mark.parametrize("pattern", list(eavc.SCAFFOLD_PATTERNS))
def test_scaffold_parses_and_lints_clean(pattern):
    # WS4-021: scaffold output parses and lints with no error-severity diagnostics.
    prog = eavc.parse(eavc.scaffold(pattern))
    diags = eavc.lint(prog)
    assert not any(d.severity == "error" for d in diags), [d.render() for d in diags]


def test_scaffold_console_program_runs():
    prog = eavc.parse(eavc.scaffold("console-program"))
    ir_text = str(eavc.lower_to_llvm(prog))
    assert 'call i32 @"puts"' in ir_text


def test_rename_updates_references():
    # WS4-014: rename updates the entity and every bare reference.
    src = open(os.path.join(EXAMPLES, "add_two.sem"), encoding="utf-8").read()
    out = eavc.rename_entity(src, "addTwoValues", "addTwo")
    assert "addTwo is operation" in out
    assert "addTwoValues" not in out
    assert "answerCall invokes addTwo" in out
    # the renamed program still lowers
    assert 'call i64 @"addTwo"' in str(eavc.lower_to_llvm(eavc.parse(out)))


def test_rename_collision_rejected():
    src = open(os.path.join(EXAMPLES, "add_two.sem"), encoding="utf-8").read()
    with pytest.raises(eavc.EavError):
        eavc.rename_entity(src, "addTwoValues", "main")  # main already exists


def test_add_operation_appends_valid_op():
    src = open(os.path.join(EXAMPLES, "add_two.sem"), encoding="utf-8").read()
    out = eavc.add_operation(src, "helperOp", "Int64")
    prog = eavc.parse(out)  # still valid
    assert prog.entities["helperOp"].fact("out").payload == ["Int64"]


def test_pack_respects_budget_and_has_sections():
    # WS4-019: pack bundles slice + diagnostics + edit-contract within budget.
    prog = eavc.parse(open(os.path.join(EXAMPLES, "add_two.sem"), encoding="utf-8").read())
    full = eavc.pack(prog, "main", budget=10000)
    assert "== slice ==" in full and "== edit-contract ==" in full
    assert "answerCall is call" in full
    clipped = eavc.pack(prog, "main", budget=80)
    assert len(clipped) <= 80


def test_slice_includes_activated_calls():
    # WS4-010: a slice of an op includes the calls it activates (with defs).
    prog = eavc.parse(open(os.path.join(EXAMPLES, "add_two.sem"), encoding="utf-8").read())
    text = eavc.slice_entity(prog, "main")
    assert "main is operation" in text
    assert "answerCall is call" in text   # activated call definition present
    assert "writeAnswer is call" in text
    assert "addTwoValues is operation" not in text  # not directly activated by main


def test_slice_reparses():
    # The slice is valid EAV (every activated call has its definition).
    prog = eavc.parse(open(os.path.join(EXAMPLES, "countdown.sem"), encoding="utf-8").read())
    text = eavc.slice_entity(prog, "main")
    re = eavc.parse(text)
    assert "main" in re.entities and "checkContinue" in re.entities


def test_lsp_completions_per_kind():
    # WS4-032: completions are the kind's §5 predicates + universal metadata.
    op = eavc.completions("operation")
    assert {"do", "branch", "effect", "let", "purpose", "invariant"} <= set(op)
    rec = eavc.completions("record")
    assert "field" in rec and "purpose" in rec and "do" not in rec


def test_lsp_hover_is_entity_contract():
    # WS4-031: hover content = the entity contract (describe).
    prog = eavc.parse(open(os.path.join(EXAMPLES, "add_two.sem"), encoding="utf-8").read())
    hover = eavc.describe(prog, "addTwoValues")
    assert "addTwoValues : operation" in hover and "out Int64" in hover


def test_lsp_diagnostics_carry_source_spans():
    # WS4-034: linter diagnostics carry a source line (squiggle target).
    prog = eavc.parse("m is module\nm path a.b\n")
    md = [d for d in eavc.lint(prog) if d.code == "MD1001"]
    assert md and md[0].line is not None


def test_lsp_rename_and_repair_actions_available():
    # WS4-033: rename (code action) + repair suggestion (quick-fix) exist.
    src = open(os.path.join(EXAMPLES, "add_two.sem"), encoding="utf-8").read()
    assert "addTwo is operation" in eavc.rename_entity(src, "addTwoValues", "addTwo")
    assert "Suggested fix:" in eavc.format_repair("SS1502")


def test_editor_tokens_move_with_parser():
    # WS4-035: keyword classification derives from the parser's reserved set —
    # a token classified `keyword` in an `is` row is the reserved `is`.
    toks = eavc.semantic_tokens("Foo is record")
    keyword_toks = {t for t, role in toks if role == "keyword"}
    assert keyword_toks <= eavc.RESERVED_WORDS


def test_semantic_tokens_subject_predicate():
    # WS4-030: column 1 = subject, column 2 = predicate; payload classified.
    toks = eavc.semantic_tokens('main let helloText immutable String "hi"')
    assert toks[0] == ("main", "subject")
    assert toks[1] == ("let", "predicate")
    assert ("immutable", "keyword") in toks
    assert ("String", "type") in toks
    assert ('"hi"', "string") in toks
    # `is` row: predicate is the `is` keyword, kind is a type
    isrow = eavc.semantic_tokens("Task is record")
    assert isrow[0] == ("Task", "subject")
    assert isrow[1] == ("is", "keyword")


def test_doctor_groups_by_severity():
    # WS4-013: doctor groups diagnostics by severity.
    prog = eavc.parse("m is module\nm path a.b\n")  # missing purpose + invariant
    groups = eavc.doctor(prog)
    assert {d.code for d in groups["error"]} >= {"MD1001", "MD1002"}
    assert isinstance(groups["warning"], list)


def test_summarize_counts_by_kind():
    prog = eavc.parse(_ir_helper_program())
    counts = eavc.summarize(prog)
    assert counts["operation"] == 2
    assert counts["call"] == 1
    assert counts["project"] == 1
    assert counts["module"] == 1


def _ir_helper_program():
    return (
        "P is project\nP module m\nP target console\nP entry main\nm is module\nm path a.b\n"
        "addTwo is operation\naddTwo in a Int64\naddTwo in b Int64\naddTwo out Int64\n"
        "addTwo do s\naddTwo return r\n"
        "s is call\ns in addTwo\ns invokes math.addInt64\n"
        "s arg left Int64 a\ns arg right Int64 b\ns out r Int64\n"
        "main is operation\nmain out ExitCode\nmain let okCode immutable ExitCode 0\n"
        "main return okCode\n"
    )


def test_discover_tests_by_lane():
    # X-004: `tag test` discovery, grouped by lane tag.
    src = (
        "checkAdd is operation\ncheckAdd out Bool\ncheckAdd tag test\ncheckAdd tag unit\n"
        "checkFlow is operation\ncheckFlow out Bool\ncheckFlow tag test\ncheckFlow tag e2e\n"
        "helper is operation\nhelper out Int64\n"  # not a test
    )
    lanes = eavc.discover_tests(eavc.parse(src))
    assert lanes["unit"] == ["checkAdd"]
    assert lanes["e2e"] == ["checkFlow"]
    assert "helper" not in {op for v in lanes.values() for op in v}


def test_contract_version_lockstep():
    # X-020: the code contract version must appear in GOVERNANCE.md (bumping the
    # version requires updating the doc).
    gov = open(os.path.join(HERE, "GOVERNANCE.md"), encoding="utf-8").read()
    assert eavc.CONTRACT_VERSION in gov


def test_governance_covers_versioning_glossary_freeze():
    # X-021/X-022/X-024: governance doc covers versioning, glossary, and the
    # §31-freeze vs §33/§34 reconciliation.
    gov = open(os.path.join(HERE, "GOVERNANCE.md"), encoding="utf-8").read()
    assert "Versioning & rollout" in gov
    assert "Glossary" in gov
    assert "freeze" in gov and "§34" in gov


def test_typed_comments_extracted_for_docs():
    # X-014: §6 metadata can migrate to typed comments; docs come from comments.
    src = (
        "main is operation\n"
        "# purpose: write the greeting and exit\n"
        "# rationale: stdout is the only effect\n"
        "main out ExitCode  # invariant: always returns a status\n"
    )
    tc = dict(eavc.typed_comments(src))
    assert tc["purpose"] == "write the greeting and exit"
    assert tc["rationale"] == "stdout is the only effect"
    assert tc["invariant"] == "always returns a status"


def test_roadmap_registers_all_gaps():
    # X-030..X-037: every §29 roadmap gap #14–#25 has a register entry.
    roadmap = open(os.path.join(HERE, "ROADMAP.md"), encoding="utf-8").read()
    for n in range(14, 26):
        assert f"## #{n} " in roadmap, f"gap #{n} missing from ROADMAP.md"


def test_token_sync_drift_guard_green():
    # X-005: every reserved word has a §5/§6/§22 home (or is a documented future
    # token). A new unsynced reserved word would make this fail.
    assert eavc.token_sync_drift() == set()


def test_token_sync_guard_detects_unsynced(monkeypatch):
    # Adding a reserved word with no home makes the guard report it.
    monkeypatch.setattr(eavc, "RESERVED_WORDS", eavc.RESERVED_WORDS | {"zzznewword"})
    assert "zzznewword" in eavc.token_sync_drift()


def test_json_surface_and_mcp_map():
    # WS4-024: --json diagnostics surface + MCP tool mappings.
    import json as _json
    prog = eavc.parse("m is module\nm path a.b\n")
    payload = _json.loads(eavc.diagnostics_json(eavc.lint(prog)))
    assert any(d["code"] == "MD1001" and d["severity"] == "error" for d in payload)
    assert all({"code", "severity", "line", "entity", "message"} <= set(d) for d in payload)
    # MCP map covers the agent-tool commands
    assert eavc.MCP_TOOL_MAP["lint"] == "check"
    assert "verify-patch" in eavc.MCP_TOOL_MAP and "slice" in eavc.MCP_TOOL_MAP


def test_lint_json_cli():
    proc = subprocess.run(
        [sys.executable, os.path.join(HERE, "eavc.py"), "lint", "--json",
         os.path.join(EXAMPLES, "hello_world.sem")],
        capture_output=True, text=True,
    )
    import json as _json
    assert _json.loads(proc.stdout) == [] or isinstance(_json.loads(proc.stdout), list)


def test_diagnostics_registry_round_trip():
    # Every registry entry has a tier + repair fields (single source of truth).
    assert eavc.DIAGNOSTICS
    for code, entry in eavc.DIAGNOSTICS.items():
        assert code[:2] in ("SS", "MD")
        assert entry["tier"] in ("T0", "T1", "T3", "T4")
        for field in ("summary", "found", "suggested"):
            assert entry[field]
        assert eavc.explain(code) is entry


def test_explain_unknown_code_errors():
    with pytest.raises(eavc.EavError):
        eavc.explain("SS9999")


def test_format_repair_has_found_and_suggested():
    text = eavc.format_repair("SS1502")
    assert "SS1502 (T0)" in text
    assert "Found:" in text
    assert "Suggested fix:" in text


def test_lint_explain_cli_registry_backed():
    # WS4-023: `lint --explain CODE` prints the registry rationale + pattern.
    proc = subprocess.run(
        [sys.executable, os.path.join(HERE, "eavc.py"), "lint", "--explain", "SS1041"],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0
    assert "SS1041" in proc.stdout and "Suggested fix:" in proc.stdout


def test_lint_module_metadata_required():
    # README §6: modules require purpose + invariant (MD1001/MD1002).
    prog = eavc.parse("m is module\nm path a.b\n")
    diags = eavc.lint(prog)
    codes = {d.code for d in diags}
    assert "MD1001" in codes and "MD1002" in codes
    assert all(d.severity == "error" for d in diags if d.code in ("MD1001", "MD1002"))


def test_lint_exported_op_metadata_required():
    # README §6: an exported operation needs purpose + invariant (MD1011/1012).
    src = (
        "m is module\nm path a.b\nm purpose \"x\"\nm invariant \"y\"\nm exports run\n"
        "run is operation\nrun out Int64\n"
    )
    codes = {d.code for d in eavc.lint(eavc.parse(src))}
    assert "MD1011" in codes and "MD1012" in codes


def test_lint_private_op_missing_purpose_is_warning_not_error():
    src = (
        "m is module\nm path a.b\nm purpose \"x\"\nm invariant \"y\"\n"
        "helper is operation\nhelper out Int64\n"  # private, no purpose
    )
    diags = eavc.lint(eavc.parse(src))
    md = [d for d in diags if d.code == "MD1021"]
    assert md and md[0].severity == "warning"


def test_lint_collects_multiple_not_bail_on_first():
    # README §29: error recovery — report N diagnostics, not just the first.
    src = "m is module\nm path a.b\n"  # missing purpose AND invariant
    diags = eavc.lint(eavc.parse(src))
    assert len([d for d in diags if d.severity == "error"]) >= 2


def test_lint_at_most_one_purpose():
    src = "thing is capability\nthing purpose \"a\"\nthing purpose \"b\"\n"
    codes = {d.code for d in eavc.lint(eavc.parse(src))}
    assert "MD1046" in codes


_MOD = "m is module\nm path a.b\nm purpose \"x\"\nm invariant \"y\"\n"


def test_suppress_removes_diagnostic_on_same_entity():
    src = _MOD + (
        "helper is operation\nhelper out Int64\n"
        'helper suppress MD1021 because "trivial private helper"\n'
    )
    diags = eavc.lint(eavc.parse(src))
    assert not any(d.code == "MD1021" for d in diags)


def test_suppress_without_because_errors():
    src = _MOD + "helper is operation\nhelper out Int64\nhelper suppress MD1021\n"
    codes = {d.code for d in eavc.lint(eavc.parse(src))}
    assert "SS5400" in codes


def test_suppress_unknown_code_errors():
    src = _MOD + 'helper is operation\nhelper out Int64\nhelper suppress SS9999 because "x"\n'
    codes = {d.code for d in eavc.lint(eavc.parse(src))}
    assert "SS5401" in codes


def test_suppress_scoped_to_entity_not_children():
    # A suppress on the module does not cover the helper op's own diagnostic.
    src = _MOD + (
        'm suppress MD1021 because "module-level suppress should not reach ops"\n'
        "helper is operation\nhelper out Int64\n"
    )
    diags = eavc.lint(eavc.parse(src))
    assert any(d.code == "MD1021" and d.entity == "helper" for d in diags)


def test_fortarget_must_name_declared_target():
    # README §30.3.1 / §17 #55: forTarget value must be a project target.
    base = (
        "App is project\nApp module m\nApp target console\nApp entry main\n"
        + _MOD
        + "main is operation\nmain out ExitCode\nmain purpose \"p\"\nmain invariant \"i\"\n"
    )
    bad = eavc.lint(eavc.parse(base + "main forTarget wasm\n"))
    assert any(d.code == "SS3010" for d in bad)
    ok = eavc.lint(eavc.parse(base + "main forTarget console\n"))
    assert not any(d.code == "SS3010" for d in ok)


def test_emitted_diagnostics_carry_codes():
    # Tagged diagnostics expose their registry code on the exception.
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(
            "main is operation\nmain out ExitCode\nmain goto nowhere\n"
        )
    assert exc.value.code == "SS1311"
    assert exc.value.code in eavc.DIAGNOSTICS


# --------------------------------------------------------------------------
# Lexer (README ss2)
# --------------------------------------------------------------------------


def test_tokenize_basic_row():
    assert eavc.tokenize_line("main do writeHello") == ["main", "do", "writeHello"]


def test_tokenize_string_keeps_spaces_and_quotes():
    toks = eavc.tokenize_line('main let t immutable String "hello world"')
    assert toks == ["main", "let", "t", "immutable", "String", '"hello world"']


def test_tokenize_full_line_comment_is_empty():
    assert eavc.tokenize_line("# this is a comment") == []


def test_tokenize_trailing_comment_stripped():
    assert eavc.tokenize_line("main async no  # ambient") == ["main", "async", "no"]


def test_tokenize_hash_inside_string_is_literal():
    toks = eavc.tokenize_line('x let c immutable String "a#b"')
    assert toks[-1] == '"a#b"'


def test_tokenize_supported_escapes():
    toks = eavc.tokenize_line(r'x let s immutable String "line\ntab\tq\"end"')
    assert toks[-1] == r'"line\ntab\tq\"end"'


def test_tokenize_hex_escape_ok():
    toks = eavc.tokenize_line(r'x let s immutable String "\xFF"')
    assert toks[-1] == r'"\xFF"'


@pytest.mark.parametrize("bad", [r'"\r"', r'"\0"'])
def test_tokenize_banned_escapes_reject(bad):
    with pytest.raises(eavc.EavError):
        eavc.tokenize_line(f"x let s immutable String {bad}")


def test_tokenize_unicode_escape_deferred():
    with pytest.raises(eavc.EavError):
        eavc.tokenize_line(r'x let s immutable String "\u{1F600}"')


def test_tokenize_equals_rejected_with_hint():
    # README ss2/ss12: `=` is not used; let is positional.
    with pytest.raises(eavc.EavError) as exc:
        eavc.tokenize_line("main let x Int64 = 5")
    assert "positional" in exc.value.message


def test_equals_in_string_is_literal():
    # `=` inside a string is fine (e.g. SQL-ish text).
    toks = eavc.tokenize_line('q let s immutable String "a = b"')
    assert toks[-1] == '"a = b"'


def test_tokenize_unterminated_string():
    with pytest.raises(eavc.EavError):
        eavc.tokenize_line('x let s immutable String "open')


# --------------------------------------------------------------------------
# Parser (README ss1, ss5, ss17 #1)
# --------------------------------------------------------------------------


def test_parse_entity_kinds_and_rows():
    prog = eavc.parse(
        "Foo is project\nFoo target console\nbar is operation\nbar out ExitCode\n"
    )
    assert prog.entities["Foo"].kind == "project"
    assert prog.entities["bar"].kind == "operation"
    assert len(prog.entities["bar"].rows) == 1


def test_crlf_normalizes_identically():
    # README ss33.2: CRLF files lex identically to LF.
    lf = "main is operation\nmain out ExitCode\nmain async no\n"
    crlf = lf.replace("\n", "\r\n")
    a, b = eavc.parse(lf), eavc.parse(crlf)
    assert list(a.entities) == list(b.entities)
    assert a.entities["main"].fact("out").payload == b.entities["main"].fact("out").payload


def test_leading_bom_stripped():
    prog = eavc.parse("﻿main is operation\nmain out ExitCode\n")
    assert "main" in prog.entities


def test_parse_first_row_must_be_is():
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse("main do writeHello\n")
    assert "must be its `is` row" in exc.value.message


def test_parse_duplicate_is_rejected():
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse("main is operation\nmain is operation\n")
    assert "duplicate" in exc.value.message


def test_parse_unknown_kind_rejected():
    with pytest.raises(eavc.EavError):
        eavc.parse("x is widget\n")


@pytest.mark.parametrize("bad", ["my_op", "my-op", "2bad", "_lead"])
def test_parse_invalid_entity_names_rejected(bad):
    # README ss2: identifiers are [a-zA-Z][a-zA-Z0-9]*.
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(f"{bad} is operation\n")
    assert "invalid entity name" in exc.value.message


def test_parse_valid_camelcase_name_ok():
    prog = eavc.parse("myOperation2 is operation\n")
    assert "myOperation2" in prog.entities


def test_parse_reserved_word_as_entity_name_rejected():
    # README ss2/ss23: `path is record` errors (path is a reserved predicate).
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse("path is record\n")
    assert "reserved word" in exc.value.message


def test_parse_reserved_word_as_variable_rejected():
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse("main is operation\nmain let type immutable Int64 0\n")
    assert "reserved word" in exc.value.message


def test_parse_reserved_word_ok_as_arg_slot_label():
    # The slot label `path` is a payload token and is exempt from reservation.
    prog = eavc.parse(
        "openDb is call\nopenDb invokes sqlite.openDatabase\n"
        "openDb arg path String dbPath\n"
    )
    assert prog.entities["openDb"].fact("arg").payload == ["path", "String", "dbPath"]


def test_parse_labeled_step_row():
    prog = eavc.parse(
        "main is operation\nmain out Int64\nmain at failed return code\n"
    )
    row = prog.entities["main"].rows[-1]
    assert row.label == "failed"
    assert row.predicate == "return"
    assert row.payload == ["code"]


def test_parse_unknown_predicate_for_kind_rejected():
    # README ss5/ss17 #22: step predicate `do` is illegal on a record.
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse("r is record\nr do something\n")
    assert "not valid for a record" in exc.value.message


def test_parse_unknown_predicate_name_rejected():
    with pytest.raises(eavc.EavError):
        eavc.parse("main is operation\nmain frobnicate x\n")


def test_parse_at_only_on_operations():
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse("r is record\nr at someLabel return x\n")
    assert "only valid on operations" in exc.value.message


def test_parse_universal_metadata_on_any_kind():
    # README ss6: purpose/invariant/tag are valid on every entity kind.
    prog = eavc.parse(
        'writer is capability\nwriter grants write console.stdout\n'
        'writer purpose "ok"\nwriter tag publicApi\n'
    )
    assert prog.entities["writer"].fact("purpose").payload == ['"ok"']


def test_parse_legal_predicate_sets_accepted():
    # One representative legal predicate per several kinds parses cleanly.
    src = (
        "E is enum\nE variant open\nE repr open 1\n"
        "A is alias\nA for Int32\n"
        "Rec is record\nRec field id Int64\n"
        "cap is capability\ncap grants read database\n"
    )
    prog = eavc.parse(src)
    assert prog.entities["E"].fact("variant").payload == ["open"]
    assert prog.entities["A"].fact("for").payload == ["Int32"]


def test_primitive_types_complete():
    for t in ("Int8", "Int64", "UInt8", "UInt64", "Float32", "Float64",
              "Bool", "String", "Void", "Byte"):
        assert t in eavc.PRIMITIVE_TYPES


def test_opaquepointer_ffi_interim_is_uint64():
    # WS3-053 / README §30.4.1: OpaquePointer/FileHandle carried as UInt64 (i64).
    src = (
        "P is project\nP module m\nP target console\nm is module\nm path a.b\n"
        "useHandle is operation\nuseHandle in h OpaquePointer\nuseHandle out OpaquePointer\n"
        "useHandle return h\n"
    )
    assert 'define i64 @"useHandle"(i64 %"h")' in _ir_for_source(src)


def test_byte_lowers_to_uint8():
    # README ss10: Byte is a primitive synonym for UInt8 -> i8 in LLVM.
    src = (
        "P is project\nP module m\nP target console\nP entry idByte\n"
        "m is module\nm path a.b\n"
        "idByte is operation\nidByte in b Byte\nidByte out Byte\nidByte return b\n"
    )
    cg = eavc.EavCodegen(eavc.parse(src))
    assert cg.resolve_type_name("Byte") == "UInt8"
    assert cg.ir_type("Byte").width == 8
    ir_text = str(cg.generate())
    assert 'define i8 @"idByte"(i8 %"b")' in ir_text


def test_errorcase_requires_of():
    # README ss9: an errorCase must declare its parent error with `of`.
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse("Failed is errorCase\nFailed payload Int32\n")
    assert "of <Error>" in exc.value.message


def test_errorcase_enumeration_by_of():
    prog = eavc.parse(
        "E is error\nA is errorCase\nA of E\n"
        "B is errorCase\nB of E\nB payload Int32\n"
    )
    cases = [
        n for n in prog.order
        if prog.entities[n].kind == "errorCase"
        and prog.entities[n].fact("of").payload == ["E"]
    ]
    assert cases == ["A", "B"]


def test_parse_result_arity_enforced():
    # README ss10: Result takes exactly OK and ERR.
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse("op is operation\nop out Result Task\n")
    assert "OK type and an ERR type" in exc.value.message
    with pytest.raises(eavc.EavError):
        eavc.parse("op is operation\nop out Result A B C\n")
    # well-formed Result parses
    prog = eavc.parse("op is operation\nop out Result Task LookupError\n")
    assert prog.entities["op"].fact("out").payload == ["Result", "Task", "LookupError"]


def test_duplicate_route_rejected():
    # README §17 #32: a webServer may not declare a duplicate METHOD+PATH route.
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(
            'srv is webServer\nsrv route GET "/x" handlerA\nsrv route GET "/x" handlerB\n'
        )
    assert exc.value.code == "SS3201"


def test_branch_else_without_guard_warns():
    # README §17 #30/#31: branch else is default-only-after-guard.
    prog = eavc.parse(
        "main is operation\nmain out ExitCode\n"
        "main let okCode immutable ExitCode 0\n"
        "main branch else target done\nmain at done return okCode\n"
    )
    assert "SS3001" in {d.code for d in eavc.lint(prog)}


def test_parse_enum_duplicate_variant_rejected():
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse("E is enum\nE variant open\nE variant open\n")
    assert "duplicate variant name" in exc.value.message


def test_parse_enum_repr_on_data_variant_rejected():
    src = "E is enum\nE variant timeout Int32\nE repr timeout 1\n"
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(src)
    assert "payloadless" in exc.value.message


def test_parse_enum_mixed_repr_rejected():
    src = "E is enum\nE variant a\nE variant b\nE repr a 1\n"
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(src)
    assert "mixes explicit and auto-assigned" in exc.value.message


def test_parse_enum_full_repr_ok():
    prog = eavc.parse(
        "E is enum\nE variant a\nE variant b\nE repr a 1\nE repr b 2\n"
    )
    assert len(prog.entities["E"].facts("repr")) == 2


def test_record_field_named_new_rejected():
    # README ss10.5/ss17 #51: `new` is the constructor target segment.
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse("T is record\nT field new Int64\n")
    assert "field named `new`" in exc.value.message


def test_alias_shadowing_primitive_rejected():
    # README ss17 #51: a primitive name can't be an alias (reserved-word rule).
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse("Int64 is alias\nInt64 for Int32\n")
    assert "reserved word" in exc.value.message


def test_parse_record_duplicate_field_rejected():
    # README ss10: duplicate field names within one record are a hard error.
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse("T is record\nT field id Int64\nT field id Int32\n")
    assert "duplicate field name" in exc.value.message


def test_parse_record_fields_keep_doc_order():
    prog = eavc.parse(
        "T is record\nT field id Int64\nT field title String\nT field done Bool\n"
    )
    fields = [r.payload[0] for r in prog.entities["T"].facts("field")]
    assert fields == ["id", "title", "done"]


def test_literal_width_range_checked():
    # README ss33.6: a literal must fit its annotated type's range.
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse("main is operation\nmain let b immutable UInt8 300\n")
    assert "out of range for UInt8" in exc.value.message
    with pytest.raises(eavc.EavError):
        eavc.parse("main is operation\nmain let i immutable Int8 200\n")
    # in range is fine; ExitCode (alias for Int32) accepts 200
    prog = eavc.parse(
        "ExitCode is alias\nExitCode for Int32\n"
        "main is operation\nmain let s immutable ExitCode 200\n"
    )
    assert "main" in prog.entities


@pytest.mark.parametrize("good", ["0", "42", "1_000", "0xFF", "0xFF_FF", "0b1010"])
def test_int_literal_accepts(good):
    prog = eavc.parse(
        f"main is operation\nmain let n immutable Int64 {good}\n"
    )
    assert prog.entities["main"].fact("let").payload[3] == good


@pytest.mark.parametrize("bad", ["007", "1__0", "1_", "0xGG", "0b12"])
def test_int_literal_rejects(bad):
    # README ss2/ss33.1: no octal/0-prefix; no leading/trailing/doubled `_`.
    with pytest.raises(eavc.EavError):
        eavc.parse(f"main is operation\nmain let n immutable Int64 {bad}\n")


def test_manifest_token_classes_recognized():
    # README ss2/ss28: repo path, semver (with pre-release/build), sha256 body.
    assert eavc.is_repo_path("github.com/ss-lang/sqlite")
    assert not eavc.is_repo_path("plainname")
    assert eavc.is_semver("v2.1.0")
    assert eavc.is_semver("v2.1.0-rc.1")
    assert eavc.is_semver("v2.1.0+build.5")
    assert not eavc.is_semver("2.1.0")  # leading v required
    assert eavc.is_sha256_digest("a" * 64)
    assert not eavc.is_sha256_digest("a" * 63)


@pytest.mark.parametrize("name", ["v2.1.0", "github.com/x/y"])
def test_manifest_tokens_rejected_as_entity_names(name):
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(f"{name} is module\n")
    assert "invalid entity name" in exc.value.message


@pytest.mark.parametrize("dur", ["50ms", "30s", "1h", "100ns", "5us", "2m"])
def test_duration_literal_recognized(dur):
    assert eavc.is_duration_literal(dur)


def test_duration_literal_flagged_unused_in_value():
    # README ss2/ss30.1.2: duration literals are reserved with no v0.3 use.
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse("main is operation\nmain let d immutable Duration 50ms\n")
    assert "reserved" in exc.value.message


@pytest.mark.parametrize("good", ["-42", "-1.5"])
def test_negative_literal_accepts(good):
    prog = eavc.parse(f"main is operation\nmain let n immutable Int64 {good}\n")
    assert prog.entities["main"].fact("let").payload[3] == good


def test_negative_literal_space_after_sign_rejected():
    # README ss2: `- 42` (space after sign) is a parse error (bare `-` token).
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse("main is operation\nmain let n immutable Int64 - 42\n")
    assert "negative literal" in exc.value.message


def test_negative_literal_leading_dot_rejected():
    with pytest.raises(eavc.EavError):
        eavc.parse("main is operation\nmain let r immutable Float64 -.5\n")


def test_float_literal_accepts():
    prog = eavc.parse("main is operation\nmain let r immutable Float64 1.5\n")
    assert prog.entities["main"].fact("let").payload[3] == "1.5"


@pytest.mark.parametrize("bad", [".5", "5.", "1.2.3"])
def test_float_literal_rejects(bad):
    # README ss2: no leading/trailing dot.
    with pytest.raises(eavc.EavError):
        eavc.parse(f"main is operation\nmain let r immutable Float64 {bad}\n")


def test_async_on_call_parses_with_deprecation_note():
    # README ss5/ss15.5: `call ... async yes` is tolerated-deprecated.
    prog = eavc.parse(
        "fetchThing is call\nfetchThing invokes net.fetch\nfetchThing async yes\n"
    )
    assert "fetchThing" in prog.entities
    assert any("deprecated" in w and "fetchThing" in w for w in prog.warnings)


def test_no_spurious_async_deprecation_for_plain_call():
    prog = eavc.parse("fetchThing is call\nfetchThing invokes net.fetch\n")
    assert not any("deprecated" in w for w in prog.warnings)


def test_parse_island_body_strips_common_indent():
    src = (
        "q is storage\n"
        "q scope module\n"
        "q body sql\n"
        "    SELECT 1\n"
        "    FROM t\n"
        "next is operation\n"
    )
    prog = eavc.parse(src)
    island = prog.islands[("q", "sql")]
    assert island == ["SELECT 1", "FROM t"]
    assert prog.entities["next"].kind == "operation"


def test_parse_tab_indent_island_rejected():
    src = "q is storage\nq body sql\n\tSELECT 1\nnext is operation\n"
    with pytest.raises(eavc.EavError):
        eavc.parse(src)


# --------------------------------------------------------------------------
# Lowering to LLVM IR (README ss18) — structural assertions on generated IR
# --------------------------------------------------------------------------


def test_module_verifies_and_has_entry():
    # The generated module must pass LLVM's verifier and define `main`.
    import llvmlite.binding as llvm

    eavc._ensure_native_init()
    ir_text = _ir_for("hello_world.sem")
    mod = llvm.parse_assembly(ir_text)
    mod.verify()  # raises on malformed IR
    assert 'define i32 @"main"()' in ir_text


def test_lower_hello_world_emits_puts_and_error_branch():
    ir_text = _ir_for("hello_world.sem")
    # console.writeLine -> puts; the fallible catch -> error test on the result.
    assert 'call i32 @"puts"' in ir_text
    assert 'icmp slt i32' in ir_text  # ifError: puts result < 0
    assert 'c"hello world\\00"' in ir_text
    # ifError branch to a `failed` block returning exit code 1, ok path 0.
    assert "failed:" in ir_text
    assert "ret i32 1" in ir_text
    assert "ret i32 0" in ir_text


def test_lower_value_call_emits_user_call_and_printf():
    ir_text = _ir_for("add_two.sem")
    # user op lowers to its own function; the call site is a real `call`.
    assert 'define i64 @"addTwoValues"(i64 %"leftValue", i64 %"rightValue")' in ir_text
    assert "add i64" in ir_text
    assert 'call i64 @"addTwoValues"(i64 40, i64 2)' in ir_text
    assert 'call i32 (i8*, ...) @"printf"' in ir_text


def test_operation_decl_rows_reorder_stable():
    # README ss11: operation declaration rows are order-independent; only `in`
    # order is significant. Generated IR must be identical when decls shuffle.
    head = (
        "P is project\nP module m\nP target console\nP entry main\n"
        "m is module\nm path a.b\n"
    )
    a = head + (
        "main is operation\nmain out ExitCode\nmain async no\nmain memory heap no\n"
        'main purpose "x"\nmain let okCode immutable ExitCode 0\nmain return okCode\n'
    )
    b = head + (
        "main is operation\nmain purpose \"x\"\nmain memory heap no\nmain async no\n"
        "main out ExitCode\nmain let okCode immutable ExitCode 0\nmain return okCode\n"
    )
    assert _ir_for_source(a) == _ir_for_source(b)


def test_lower_webserver_target_rejected():
    src = "W is project\nW module m\nW target webServer\nW entry s\nm is module\nm path a.b\n"
    with pytest.raises(eavc.EavError) as exc:
        eavc.lower_to_llvm(eavc.parse(src))
    assert "console code generator" in exc.value.message


def test_lower_mutable_rebind_stores_to_alloca():
    # README ss12: a `let mutable` is an alloca; out-rebind is a store.
    ir_text = _ir_for("countdown.sem")
    assert 'alloca i64' in ir_text          # mutable counter
    assert 'store i64' in ir_text           # rebind via store
    assert 'sub i64' in ir_text             # decrementCounter


def test_div_by_zero_emits_trap_guard():
    # README ss10.6: integer divide/modulo by zero traps (no UB).
    src = (
        "P is project\nP module m\nP target console\nP entry divide\nm is module\nm path a.b\n"
        "divide is operation\ndivide in a Int64\ndivide in b Int64\ndivide out Int64\n"
        "divide do q\ndivide return r\n"
        "q is call\nq in divide\nq invokes math.divideInt64\n"
        "q arg left Int64 a\nq arg right Int64 b\nq out r Int64\n"
    )
    ir_text = _ir_for_source(src)
    assert "divByZero:" in ir_text
    assert 'call void @"llvm.trap"()' in ir_text
    assert "sdiv i64" in ir_text


def test_compare_primitive_lowers_to_icmp():
    src = (
        "P is project\nP module m\nP target console\nP entry cmp\nm is module\nm path a.b\n"
        "cmp is operation\ncmp in a Int64\ncmp in b Int64\ncmp out Bool\n"
        "cmp do cmpCall\ncmp return r\n"
        "cmpCall is call\ncmpCall in cmp\ncmpCall invokes compare.lessThanInt64\n"
        "cmpCall arg left Int64 a\ncmpCall arg right Int64 b\ncmpCall out r Bool\n"
    )
    assert "icmp slt i64" in _ir_for_source(src)


def test_record_fieldwise_equality_and_ordering_rejected():
    # README §33.7: records compare by deep fieldwise equality; ordering invalid.
    base = (
        "P is project\nP module m\nP target console\nm is module\nm path a.b\n"
        "Point is record\nPoint field x Int64\nPoint field y Int64\n"
        "eqOp is operation\neqOp in a Point\neqOp in b Point\neqOp out Bool\n"
        "eqOp do cmpCall\neqOp return r\n"
        "cmpCall is call\ncmpCall in eqOp\ncmpCall invokes compare.equalPoint\n"
        "cmpCall arg left Point a\ncmpCall arg right Point b\ncmpCall out r Bool\n"
    )
    ir_text = _ir_for_source(base)
    assert "extractvalue" in ir_text
    assert "icmp eq i64" in ir_text
    assert "and i1" in ir_text
    # ordering on a record is rejected
    ordering = base.replace("compare.equalPoint", "compare.greaterThanPoint")
    with pytest.raises(eavc.EavError) as exc:
        eavc.lower_to_llvm(eavc.parse(ordering))
    assert exc.value.code == "SS1345"


def test_compare_string_equality_bytewise():
    # README §10.6: String equality is bytewise via strcmp.
    src = (
        "P is project\nP module m\nP target console\nP entry eq\nm is module\nm path a.b\n"
        "eq is operation\neq in a String\neq in b String\neq out Bool\n"
        "eq do cmpCall\neq return r\n"
        "cmpCall is call\ncmpCall in eq\ncmpCall invokes compare.equalString\n"
        "cmpCall arg left String a\ncmpCall arg right String b\ncmpCall out r Bool\n"
    )
    ir_text = _ir_for_source(src)
    assert 'call i32 @"strcmp"' in ir_text
    assert "icmp eq i32" in ir_text


def test_compare_ordering_on_string_rejected():
    src = (
        "P is project\nP module m\nP target console\nP entry cmp\nm is module\nm path a.b\n"
        "cmp is operation\ncmp in a String\ncmp in b String\ncmp out Bool\n"
        "cmp do cmpCall\ncmp return r\n"
        "cmpCall is call\ncmpCall in cmp\ncmpCall invokes compare.lessThanString\n"
        "cmpCall arg left String a\ncmpCall arg right String b\ncmpCall out r Bool\n"
    )
    with pytest.raises(eavc.EavError) as exc:
        eavc.lower_to_llvm(eavc.parse(src))
    assert exc.value.code == "SS1345"


def test_compare_ordering_on_bool_rejected():
    # README §17 #45: Bool/enum are equals-only.
    src = (
        "P is project\nP module m\nP target console\nP entry cmp\nm is module\nm path a.b\n"
        "cmp is operation\ncmp in a Bool\ncmp in b Bool\ncmp out Bool\n"
        "cmp do cmpCall\ncmp return r\n"
        "cmpCall is call\ncmpCall in cmp\ncmpCall invokes compare.greaterThanBool\n"
        "cmpCall arg left Bool a\ncmpCall arg right Bool b\ncmpCall out r Bool\n"
    )
    with pytest.raises(eavc.EavError) as exc:
        eavc.lower_to_llvm(eavc.parse(src))
    assert exc.value.code == "SS1345"


def test_heap_no_record_build_compiles():
    # README §10.6: ordinary values are compiler-managed; a record-building op
    # satisfies `memory heap no` (no allocator, no free).
    prog = eavc.parse(open(os.path.join(EXAMPLES, "record_demo.sem"), encoding="utf-8").read())
    assert prog.entities["main"].fact("memory").payload == ["heap", "no"]
    ir_text = str(eavc.lower_to_llvm(prog))
    assert "insertvalue" in ir_text  # record built in registers, no heap


def test_core_primitives_available_without_import():
    # WS3-010: primitive types are built-in; usable with no `imports` row.
    src = (
        "P is project\nP module m\nP target console\nm is module\nm path a.b\n"
        "widths is operation\nwidths in a Int8\nwidths in b UInt64\n"
        "widths in c Float32\nwidths in d Bool\nwidths out Bool\nwidths return d\n"
    )
    ir_text = _ir_for_source(src)
    assert 'define i1 @"widths"(i8 %"a", i64 %"b", float %"c", i1 %"d")' in ir_text


def test_arg_document_order_preserved():
    # README §10.6: a call's args bind in document order (left then right), so
    # subtractInt64(a, b) lowers to `sub a, b`, not `sub b, a`.
    src = (
        "P is project\nP module m\nP target console\nm is module\nm path a.b\n"
        "sub2 is operation\nsub2 in a Int64\nsub2 in b Int64\nsub2 out Int64\n"
        "sub2 do s\nsub2 return r\n"
        "s is call\ns in sub2\ns invokes math.subtractInt64\n"
        "s arg left Int64 a\ns arg right Int64 b\ns out r Int64\n"
    )
    assert 'sub i64 %"a", %"b"' in _ir_for_source(src)


def test_ieee_float_compare_nan_semantics():
    # README ss10.6: NaN != NaN is true (unordered une); NaN == NaN is false
    # (ordered oeq). The comparator choice in IR encodes IEEE-754 semantics.
    src = (
        "P is project\nP module m\nP target console\nP entry cmp\nm is module\nm path a.b\n"
        "cmp is operation\ncmp in a Float64\ncmp in b Float64\ncmp out Bool\n"
        "cmp do ne\ncmp do eq\ncmp return neResult\n"
        "ne is call\nne in cmp\nne invokes math.notEqualFloat64\n"
        "ne arg left Float64 a\nne arg right Float64 b\nne out neResult Bool\n"
        "eq is call\neq in cmp\neq invokes math.equalFloat64\n"
        "eq arg left Float64 a\neq arg right Float64 b\neq out eqResult Bool\n"
    )
    ir_text = _ir_for_source(src)
    assert "fcmp une double" in ir_text  # notEquals -> unordered (NaN != NaN true)
    assert "fcmp oeq double" in ir_text  # equals -> ordered (NaN == NaN false)


def test_lower_immutable_rebind_rejected():
    # README ss12 / ss17 #28: `out` to a `let immutable` is a hard error.
    src = (
        "P is project\nP module m\nP target console\nP entry main\n"
        "m is module\nm path a.b\n"
        "main is operation\nmain out ExitCode\n"
        "main let total immutable Int64 0\n"
        "main do addCall\nmain return total\n"
        "addCall is call\naddCall in main\naddCall invokes math.addInt64\n"
        "addCall arg left Int64 total\naddCall arg right Int64 total\n"
        "addCall out total Int64\n"
    )
    with pytest.raises(eavc.EavError) as exc:
        eavc.lower_to_llvm(eavc.parse(src))
    assert "immutable" in exc.value.message


def test_lower_branch_iffalse_inverts_to_cbranch():
    # README ss13: `branch ifFalse COND goto L` -> cbranch(cond, fallthrough, L).
    ir_text = _ir_for("countdown.sem")
    assert "icmp sge i64" in ir_text                 # checkContinue
    assert "loopExit:" in ir_text
    # cond-true continues into the loop body; cond-false jumps to loopExit.
    assert "br i1 " in ir_text


def test_branch_if_lowers_and_unbound_condition_rejected():
    # README ss13/ss17 #8: `branch if COND goto L` needs a Bool in scope.
    good = (
        "P is project\nP module m\nP target console\nP entry main\n"
        "m is module\nm path a.b\n"
        "main is operation\nmain out ExitCode\n"
        "main let flag immutable Bool true\nmain let okCode immutable ExitCode 0\n"
        "main branch if flag goto done\nmain return okCode\n"
        "main at done return okCode\n"
    )
    ir_text = _ir_for_source(good)
    assert "br i1 " in ir_text
    bad = good.replace("branch if flag goto done", "branch if missingFlag goto done")
    with pytest.raises(eavc.EavError) as exc:
        eavc.lower_to_llvm(eavc.parse(bad))
    assert "not in scope" in exc.value.message


def test_body_runtimebinding_rejects_steps():
    # README ss11: a non-step body has no step rows.
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(
            "cmp is operation\ncmp body runtimeBinding runtime.cstring.compare\n"
            "cmp let x immutable Int64 0\ncmp do someCall\n"
        )
    assert "non-step body has no steps" in exc.value.message


def test_body_runtimebinding_is_declaration_only():
    src = (
        "P is project\nP module m\nP target console\nP entry main\n"
        "m is module\nm path a.b\n"
        "cmp is operation\ncmp in a Int64\ncmp out Int64\n"
        "cmp body runtimeBinding runtime.thing\n"
        "main is operation\nmain out ExitCode\n"
        "main let okCode immutable ExitCode 0\nmain return okCode\n"
    )
    ir_text = _ir_for_source(src)
    # README ss11/ss26: a runtimeBinding op lowers to a bare extern *named after
    # the bound ABI symbol* (not the op), so a call to it links to that symbol.
    assert 'declare i64 @"runtime.thing"(i64' in ir_text
    assert 'define i64 @"cmp"' not in ir_text  # not defined with a body


def test_return_arity_void_op_rejects_value():
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(
            "main is operation\nmain let x immutable Int64 1\nmain return x\n"
        )
    assert "returns void" in exc.value.message


def test_return_arity_result_rejects_both_nil_and_both_value():
    base = (
        "look is operation\nlook out Result Task LookupError\n"
        "look let t immutable Int64 1\nlook let e immutable Int64 2\n"
    )
    with pytest.raises(eavc.EavError):  # both nil
        eavc.parse(base + "look return nil nil\n")
    with pytest.raises(eavc.EavError):  # both value
        eavc.parse(base + "look return t e\n")
    # one value + one nil is well-formed
    prog = eavc.parse(base + "look return t nil\n")
    assert "look" in prog.entities


def test_return_arity_single_rejects_void_return():
    with pytest.raises(eavc.EavError):
        eavc.parse("get is operation\nget out Int64\nget return void\n")


def test_sqlite_column_used_after_step_warns():
    # README §17 #23 (semsc SS3113): a borrowed columnText pointer used AFTER a
    # later step on the same statement is a use-after-invalidation. (No-op-failing:
    # the old rule flagged the wrong site; a no-op lowering would not flag at all.)
    src = (
        "main is operation\nmain out ExitCode\nmain async no\n"
        "main let okCode immutable ExitCode 0\nmain let stmt immutable SqliteStatement 1\n"
        "main do readTitle\nmain do stepRow\nmain do useTitle\nmain return okCode\n"
        "readTitle is call\nreadTitle in main\nreadTitle invokes sqlite.columnText\n"
        "readTitle arg statement SqliteStatement stmt\nreadTitle out title String\n"
        "stepRow is call\nstepRow in main\nstepRow invokes sqlite.stepStatement\n"
        "stepRow arg statement SqliteStatement stmt\nstepRow discards \"x\"\n"
        "useTitle is call\nuseTitle in main\nuseTitle invokes console.writeLine\n"
        "useTitle arg text String title\n"
    )
    assert "SS1901" in {d.code for d in eavc.lint(eavc.parse(src))}


def test_sqlite_sibling_column_reads_no_warning():
    # Reading several columns from one row before stepping is the idiomatic
    # pattern: sibling column reads do NOT invalidate each other, and scalar
    # columnInt64 copies are never borrowed. Neither must warn.
    src = (
        "main is operation\nmain out ExitCode\nmain async no\n"
        "main let okCode immutable ExitCode 0\nmain let stmt immutable SqliteStatement 1\n"
        "main do readId\nmain do readTitle\nmain do useTitle\nmain do stepRow\nmain return okCode\n"
        "readId is call\nreadId in main\nreadId invokes sqlite.columnInt64\n"
        "readId arg statement SqliteStatement stmt\nreadId out rowId Int64\n"
        "readTitle is call\nreadTitle in main\nreadTitle invokes sqlite.columnText\n"
        "readTitle arg statement SqliteStatement stmt\nreadTitle out title String\n"
        "useTitle is call\nuseTitle in main\nuseTitle invokes console.writeLine\n"
        "useTitle arg text String title\n"
        "stepRow is call\nstepRow in main\nstepRow invokes sqlite.stepStatement\n"
        "stepRow arg statement SqliteStatement stmt\nstepRow discards \"x\"\n"
    )
    assert "SS1901" not in {d.code for d in eavc.lint(eavc.parse(src))}


def _two_prepared_writes(body_steps, extra_calls=""):
    # body_steps: the `main do ...` lines (transaction calls interleaved or not).
    return (
        "insertSql is storage\ninsertSql scope module\ninsertSql type SqlText\n"
        "insertSql mutability immutable\ninsertSql body sql\n  INSERT INTO t VALUES (?)\n\n"
        "main is operation\nmain out ExitCode\nmain async no\n"
        "main let okCode immutable ExitCode 0\nmain let db immutable SqliteDatabase 1\n"
        + body_steps + "main return okCode\n"
        "prepA is call\nprepA in main\nprepA invokes sqlite.prepareStatement\n"
        "prepA arg database SqliteDatabase db\nprepA arg sql SqlText insertSql\nprepA out stA SqliteStatement\n"
        "stepA is call\nstepA in main\nstepA invokes sqlite.stepStatement\n"
        "stepA arg statement SqliteStatement stA\nstepA discards \"x\"\n"
        "prepB is call\nprepB in main\nprepB invokes sqlite.prepareStatement\n"
        "prepB arg database SqliteDatabase db\nprepB arg sql SqlText insertSql\nprepB out stB SqliteStatement\n"
        "stepB is call\nstepB in main\nstepB invokes sqlite.stepStatement\n"
        "stepB arg statement SqliteStatement stB\nstepB discards \"x\"\n"
        + extra_calls
    )


def test_sqlite_multi_write_without_transaction_warns():
    # README §17 #24 (semsc SS3635): two prepared+stepped INSERTs with no
    # BEGIN/COMMIT warn. CREATE/exec-of-non-write are not counted as writes.
    src = _two_prepared_writes("main do prepA\nmain do stepA\nmain do prepB\nmain do stepB\n")
    assert "SS1902" in {d.code for d in eavc.lint(eavc.parse(src))}


def test_sqlite_multi_write_with_exec_transaction_no_warning():
    # `sqlite.exec` of BEGIN.../COMMIT... around the writes (the original
    # taskforge-web idiom) makes the boundary visible -> no warning.
    src = _two_prepared_writes(
        "main do beginTx\nmain do prepA\nmain do stepA\n"
        "main do prepB\nmain do stepB\nmain do commitTx\n",
        extra_calls=(
            "beginSql is storage\nbeginSql scope module\nbeginSql type SqlText\n"
            "beginSql mutability immutable\nbeginSql body sql\n  BEGIN IMMEDIATE\n\n"
            "commitSql is storage\ncommitSql scope module\ncommitSql type SqlText\n"
            "commitSql mutability immutable\ncommitSql body sql\n  COMMIT\n\n"
            "beginTx is call\nbeginTx in main\nbeginTx invokes sqlite.exec\n"
            "beginTx arg database SqliteDatabase db\nbeginTx arg sql SqlText beginSql\nbeginTx discards \"x\"\n"
            "commitTx is call\ncommitTx in main\ncommitTx invokes sqlite.exec\n"
            "commitTx arg database SqliteDatabase db\ncommitTx arg sql SqlText commitSql\ncommitTx discards \"x\"\n"
        ),
    )
    assert "SS1902" not in {d.code for d in eavc.lint(eavc.parse(src))}


def test_out_referenced_before_do_rejected():
    # README §25 / WS2-050: a call result used before the `do` that produces it.
    src = (
        "main is operation\nmain out ExitCode\nmain async no\n"
        "main let okCode immutable ExitCode 0\n"
        "main let a immutable Int64 1\nmain let b immutable Int64 2\n"
        "main do useIt\nmain do produceIt\nmain return okCode\n"
        "useIt is call\nuseIt in main\nuseIt invokes console.writeIntegerLine\n"
        "useIt arg value Int64 produced\n"
        "produceIt is call\nproduceIt in main\nproduceIt invokes math.addInt64\n"
        "produceIt arg left Int64 a\nproduceIt arg right Int64 b\n"
        "produceIt out produced Int64\n"
    )
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(src)
    assert getattr(exc.value, "code", None) == "SS2502"


def test_catch_var_off_error_path_rejected():
    # README §25 / WS2-050: a catch variable used on the straight-line success
    # path (not the ifError path) is unbound.
    src = (
        "main is operation\nmain out ExitCode\nmain async no\n"
        "main effect write console.stdout\nmain uses w\n"
        "main let okCode immutable ExitCode 0\nmain let msg immutable String \"x\"\n"
        "main do riskyCall\nmain do useErr\nmain return okCode\n"
        "w is capability\nw grants write console.stdout\nw purpose \"p\"\n"
        "riskyCall is call\nriskyCall in main\nriskyCall invokes console.writeLine\n"
        "riskyCall arg text String msg\nriskyCall catch writeErr ConsoleWriteError\n"
        "riskyCall discards \"demo\"\n"
        "useErr is call\nuseErr in main\nuseErr invokes console.writeLine\n"
        "useErr arg text String writeErr\n"
    )
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(src)
    assert getattr(exc.value, "code", None) == "SS2502"


def test_join_before_start_rejected():
    # README §13 / WS2-050: joining a task before it is started.
    src = (
        "main is operation\nmain out ExitCode\nmain async yes\n"
        "main let okCode immutable ExitCode 0\n"
        "main join fetchTask\nmain return okCode\n"
        "fetchTask is task\nfetchTask in main\nfetchTask invokes x.fetch\n"
    )
    with pytest.raises(eavc.EavError):
        eavc.parse(src)


def test_invoke_ambiguity_builtin_namespace_rejected():
    # README §17 #51: an operation named for a built-in namespace is ambiguous.
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse("console is operation\nconsole out Int64\nconsole return one\n")
    assert getattr(exc.value, "code", None) == "SS1552"


def test_import_alias_collides_with_type_rejected():
    # README §17 #51: an import alias equal to a declared type name is ambiguous.
    src = (
        "Json is alias\nJson for String\n"
        "app is module\napp path demo.app\napp purpose \"p\"\napp invariant \"i\"\n"
        "app imports Json standard.json\n"
    )
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(src)
    assert getattr(exc.value, "code", None) == "SS1551"


def test_ifvariant_bind_payloadless_rejected():
    # README §17 #53: `bind` on a payloadless variant is a hard error.
    src = (
        "Status is enum\nStatus variant open\nStatus variant done\n"
        "main is operation\nmain out ExitCode\nmain async no\n"
        "main let okCode immutable ExitCode 0\n"
        "main do makeStatus\n"
        "main branch ifVariant currentStatus done bind p goto isDone\n"
        "main at isDone return okCode\n"
        "makeStatus is call\nmakeStatus in main\n"
        "makeStatus invokes Status.done\nmakeStatus out currentStatus Status\n"
    )
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(src)
    assert getattr(exc.value, "code", None) == "SS1354"


def test_variant_match_golden_is_exhaustive_no_warning():
    # variant_match matches `done` and falls through to a default arm
    # (writeOpen; return) for `open` -> exhaustive-by-default, no SS1353.
    prog = eavc.parse(open(os.path.join(EXAMPLES, "variant_match.sem"), encoding="utf-8").read())
    assert "SS1353" not in {d.code for d in eavc.lint(prog)}


def test_non_exhaustive_ifvariant_warns():
    # README §17 #52: matching a subset of variants then falling straight into a
    # labeled arm (no default for the unmatched variant) warns SS1353.
    src = (
        "Status is enum\nStatus variant open\nStatus variant done\n"
        "main is operation\nmain out ExitCode\nmain async no\n"
        "main let okCode immutable ExitCode 0\n"
        "main do makeStatus\n"
        "main branch ifVariant currentStatus done goto isDone\n"
        "main at isDone return okCode\n"
        "makeStatus is call\nmakeStatus in main\n"
        "makeStatus invokes Status.done\nmakeStatus out currentStatus Status\n"
    )
    assert "SS1353" in {d.code for d in eavc.lint(eavc.parse(src))}


def test_exhaustive_ifvariant_no_warning():
    # Covering every variant needs no default arm.
    src = (
        "Status is enum\nStatus variant open\nStatus variant done\n"
        "main is operation\nmain out ExitCode\nmain async no\n"
        "main let okCode immutable ExitCode 0\n"
        "main do makeStatus\n"
        "main branch ifVariant currentStatus done goto isDone\n"
        "main branch ifVariant currentStatus open goto isOpen\n"
        "main at isDone return okCode\n"
        "main at isOpen return okCode\n"
        "makeStatus is call\nmakeStatus in main\n"
        "makeStatus invokes Status.done\nmakeStatus out currentStatus Status\n"
    )
    assert "SS1353" not in {d.code for d in eavc.lint(eavc.parse(src))}


def test_mixed_predecessor_bind_rejected():
    # README §13 / WS1-064: a name bound to two different types on two branches
    # that merge at a shared label is a definite-assignment error.
    src = (
        "main is operation\nmain out ExitCode\nmain async no\n"
        "main let flag immutable Bool true\n"
        "main branch if flag goto elseBlock\n"
        "main do bindInt\nmain goto joinBlock\n"
        "main at elseBlock do bindStr\nmain goto joinBlock\n"
        "main at joinBlock let okCode immutable ExitCode 0\nmain return okCode\n"
        "bindInt is call\nbindInt in main\nbindInt invokes x.a\nbindInt out merged Int64\n"
        "bindStr is call\nbindStr in main\nbindStr invokes x.b\nbindStr out merged String\n"
    )
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(src)
    assert getattr(exc.value, "code", None) == "SS1064"


def test_consistent_predecessor_bind_ok():
    # Same name + same type on both branches merges cleanly.
    src = (
        "main is operation\nmain out ExitCode\nmain async no\n"
        "main let flag immutable Bool true\n"
        "main branch if flag goto elseBlock\n"
        "main do bindA\nmain goto joinBlock\n"
        "main at elseBlock do bindB\nmain goto joinBlock\n"
        "main at joinBlock let okCode immutable ExitCode 0\nmain return okCode\n"
        "bindA is call\nbindA in main\nbindA invokes x.a\nbindA out merged Int64\n"
        "bindB is call\nbindB in main\nbindB invokes x.b\nbindB out merged Int64\n"
    )
    eavc.parse(src)  # no raise


_RANDOM_SEQ_MAIN = """
RandomSeq is project
RandomSeq module appRandom
RandomSeq target console
RandomSeq entry main

appRandom is module
appRandom path examples.randomSeq
appRandom exports main
appRandom purpose "Advance a seeded PRNG one step"
appRandom invariant "Deterministic from the fixed seed"

ExitCode is alias
ExitCode for Int32

main is operation
main out ExitCode
main async no
main purpose "Advance the PRNG from seed 1 and print the next state"
main invariant "Prints the deterministic next state for seed 1"
main let seed immutable Int64 1
main let okCode immutable ExitCode 0
main do step
main do show
main return okCode

step is call
step in main
step invokes nextRandom
step arg state Int64 seed
step out nextState Int64

show is call
show in main
show invokes console.writeIntegerLine
show arg value Int64 nextState
"""


def test_random_seeded_sequence_is_deterministic():
    # WS3-103: the pure LCG gives the same next state for the same seed.
    stdlib = open(os.path.join(STD, "standard.random.sem"), encoding="utf-8").read()
    composed = stdlib + "\n" + _RANDOM_SEQ_MAIN
    proc = subprocess.run(
        [sys.executable, os.path.join(HERE, "eavc.py"), "run", "-"],
        input=composed, capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "7806831264735756412"  # LCG(seed=1)


def test_random_seed_from_entropy_requires_capability():
    # WS3-103: drawing a seed from entropy is capability-mediated.
    stdlib = open(os.path.join(STD, "standard.random.sem"), encoding="utf-8").read()
    main = (
        "RandSeed is project\nRandSeed module appRandSeed\n"
        "RandSeed target console\nRandSeed entry main\n"
        "appRandSeed is module\nappRandSeed path examples.randSeed\n"
        'appRandSeed exports main\nappRandSeed purpose "p"\nappRandSeed invariant "i"\n'
        "ExitCode is alias\nExitCode for Int32\n"
        "main is operation\nmain out ExitCode\nmain async no\n"
        'main purpose "p"\nmain invariant "i"\n'
        "main let okCode immutable ExitCode 0\n"
        "main do draw\nmain do show\nmain return okCode\n"
        "draw is call\ndraw in main\ndraw invokes seedFromEntropy\ndraw out s Int64\n"
        "show is call\nshow in main\nshow invokes console.writeIntegerLine\nshow arg value Int64 s\n"
    )
    prog = eavc.parse(stdlib + "\n" + main)
    assert any("read random.entropy" in w and "not covered" in w for w in prog.warnings)


_CLOCK_CONV_MAIN = """
ClockConv is project
ClockConv module appClock
ClockConv target console
ClockConv entry main

appClock is module
appClock path examples.clockConv
appClock exports main
appClock purpose "Convert seconds to minutes via standard.clock"
appClock invariant "Prints the whole-minute count"

ExitCode is alias
ExitCode for Int32

main is operation
main out ExitCode
main async no
main purpose "Convert 120 seconds to minutes and print it"
main invariant "Prints 2"
main let seconds immutable Int64 120
main let okCode immutable ExitCode 0
main do convert
main do show
main return okCode

convert is call
convert in main
convert invokes secondsToMinutes
convert arg seconds Int64 seconds
convert out minutes Int64

show is call
show in main
show invokes console.writeIntegerLine
show arg value Int64 minutes
"""


def test_clock_pure_conversion_jit_runs():
    # WS3-102: pure time-unit conversions JIT-run (no clock authority needed).
    stdlib = open(os.path.join(STD, "standard.clock.sem"), encoding="utf-8").read()
    composed = stdlib + "\n" + _CLOCK_CONV_MAIN
    proc = subprocess.run(
        [sys.executable, os.path.join(HERE, "eavc.py"), "run", "-"],
        input=composed, capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "2"  # 120s -> 2min


def test_clock_read_requires_capability():
    # WS3-102: a wall-clock read is capability-mediated — a caller that activates
    # nowMillis without a covering capability is flagged.
    stdlib = open(os.path.join(STD, "standard.clock.sem"), encoding="utf-8").read()
    main = (
        "ClockRead is project\nClockRead module appClockRead\n"
        "ClockRead target console\nClockRead entry main\n"
        "appClockRead is module\nappClockRead path examples.clockRead\n"
        'appClockRead exports main\nappClockRead purpose "p"\nappClockRead invariant "i"\n'
        "ExitCode is alias\nExitCode for Int32\n"
        "main is operation\nmain out ExitCode\nmain async no\n"
        'main purpose "p"\nmain invariant "i"\n'
        "main let okCode immutable ExitCode 0\n"
        "main do readClock\nmain do show\nmain return okCode\n"
        "readClock is call\nreadClock in main\nreadClock invokes nowMillis\n"
        "readClock out t Int64\n"
        "show is call\nshow in main\nshow invokes console.writeIntegerLine\n"
        "show arg value Int64 t\n"
    )
    prog = eavc.parse(stdlib + "\n" + main)
    assert any("read clock.wall" in w and "not covered" in w for w in prog.warnings)


_PROCESS_EXIT_MAIN = """
ProcExit is project
ProcExit module appProc
ProcExit target console
ProcExit entry main

appProc is module
appProc path examples.procExit
appProc exports main
appProc purpose "Exit with a chosen process code"
appProc invariant "Returns the requested exit code"

ExitCode is alias
ExitCode for Int32

main is operation
main out ExitCode
main async no
main purpose "Call process exit with code 3"
main invariant "Terminates with code 3"
{cap}main let code immutable Int32 3
main let okCode immutable ExitCode 0
main do callExit
main return okCode

callExit is call
callExit in main
callExit invokes exitProcess
callExit arg code Int32 code
"""


def test_process_exit_returns_code_through_runtime():
    # WS3-101: a program calling process exit returns the given code (libc exit).
    stdlib = open(os.path.join(STD, "standard.process.sem"), encoding="utf-8").read()
    cap = "main effect terminate process.self\nmain uses processTerminator\n"
    composed = stdlib + "\n" + _PROCESS_EXIT_MAIN.format(cap=cap)
    proc = subprocess.run(
        [sys.executable, os.path.join(HERE, "eavc.py"), "run", "-"],
        input=composed, capture_output=True, text=True,
    )
    assert proc.returncode == 3


def test_process_exit_requires_covering_capability():
    # WS3-101: termination is capability-mediated — without a covering capability
    # the effective `terminate process.self` effect is flagged.
    stdlib = open(os.path.join(STD, "standard.process.sem"), encoding="utf-8").read()
    composed = stdlib + "\n" + _PROCESS_EXIT_MAIN.format(cap="")
    prog = eavc.parse(composed)
    assert any("terminate process.self" in w and "not covered" in w
               for w in prog.warnings)


def test_math_int_ops_jit_run():
    # WS3-100: extended pure Int64 math targets JIT-run to their expected values.
    src = (
        "P is project\nP module m\nP target console\nP entry main\n"
        'm is module\nm path a.b\nm purpose "p"\nm invariant "i"\nm exports main\n'
        "ExitCode is alias\nExitCode for Int32\n"
        "main is operation\nmain out ExitCode\nmain async no\n"
        'main purpose "p"\nmain invariant "i"\n'
        "main let n immutable Int64 7\nmain let okCode immutable ExitCode 0\n"
        "main do popcount\nmain do show\nmain return okCode\n"
        "popcount is call\npopcount in main\npopcount invokes math.popcountInt64\n"
        "popcount arg value Int64 n\npopcount out bitCount Int64\n"
        "show is call\nshow in main\nshow invokes console.writeIntegerLine\n"
        "show arg value Int64 bitCount\n"
    )
    proc = subprocess.run(
        [sys.executable, os.path.join(HERE, "eavc.py"), "run", "-"],
        input=src, capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "3"  # popcount(7) == 3


def test_math_float_sqrt_jit_run():
    # WS3-100: Float64 unary intrinsics (llvm.sqrt) JIT-run.
    src = (
        "P is project\nP module m\nP target console\nP entry main\n"
        'm is module\nm path a.b\nm purpose "p"\nm invariant "i"\nm exports main\n'
        "ExitCode is alias\nExitCode for Int32\n"
        "main is operation\nmain out ExitCode\nmain async no\n"
        'main purpose "p"\nmain invariant "i"\n'
        "main let x immutable Float64 16.0\nmain let okCode immutable ExitCode 0\n"
        "main do root\nmain do show\nmain return okCode\n"
        "root is call\nroot in main\nroot invokes math.sqrtFloat64\n"
        "root arg value Float64 x\nroot out result Float64\n"
        "show is call\nshow in main\nshow invokes console.writeFloatLine\n"
        "show arg value Float64 result\n"
    )
    ir_text = eavc._ir_for_source(src) if hasattr(eavc, "_ir_for_source") else str(
        eavc.lower_to_llvm(eavc.parse(src)))
    assert "llvm.sqrt" in ir_text
    proc = subprocess.run(
        [sys.executable, os.path.join(HERE, "eavc.py"), "run", "-"],
        input=src, capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "4"  # sqrt(16.0) == 4


def _storage_program(mutability, with_effect):
    cap = ""
    eff = ""
    if with_effect:
        cap = (
            "counterWriter is capability\ncounterWriter grants write storage.counter\n"
            'counterWriter purpose "Authority to mutate the counter global"\n'
        )
        eff = "main effect write storage.counter\nmain uses counterWriter\n"
    return (
        "P is project\nP module m\nP target console\nP entry main\n"
        'm is module\nm path a.b\nm purpose "p"\nm invariant "i"\nm exports main\n'
        "ExitCode is alias\nExitCode for Int32\n"
        + cap +
        "counter is storage\ncounter scope module\ncounter type Int64\n"
        f"counter mutability {mutability}\ncounter value 0\n"
        "main is operation\nmain out ExitCode\nmain async no\n"
        'main purpose "p"\nmain invariant "i"\n' + eff +
        "main let step immutable Int64 1\nmain let okCode immutable ExitCode 0\n"
        "main do bump\nmain return okCode\n"
        "bump is call\nbump in main\nbump invokes math.addInt64\n"
        "bump arg left Int64 counter\nbump arg right Int64 step\nbump out counter Int64\n"
    )


def test_out_rebinds_immutable_storage_rejected():
    # WS1-085: out targeting an immutable module storage entity is a hard error.
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(_storage_program("immutable", with_effect=False))
    assert getattr(exc.value, "code", None) == "SS1085"


def test_out_mutable_storage_missing_effect_warns():
    # WS1-085: rebinding mutable storage without a storage effect warns SS1086.
    prog = eavc.parse(_storage_program("mutable", with_effect=False))
    assert "SS1086" in {d.code for d in eavc.lint(prog)}


def test_out_mutable_storage_with_effect_lowers():
    # WS1-085: with the storage effect + capability, the rebind is clean and the
    # codegen stores the call result into the module global.
    prog = eavc.parse(_storage_program("mutable", with_effect=True))
    assert "SS1086" not in {d.code for d in eavc.lint(prog)}
    ir_text = str(eavc.lower_to_llvm(prog))
    assert 'store' in ir_text and '@"counter"' in ir_text


_OPTYPE_BASE = (
    "Int64Endo is operationType\nInt64Endo in Int64\nInt64Endo out Int64\n"
    "double is operation\ndouble in n Int64\ndouble out Int64\n"
    "double let two immutable Int64 2\n"
    "double do mulCall\ndouble return doubled\n"
    "mulCall is call\nmulCall in double\nmulCall invokes math.multiplyInt64\n"
    "mulCall arg left Int64 n\nmulCall arg right Int64 two\nmulCall out doubled Int64\n"
    "main is operation\nmain out ExitCode\nmain async no\n"
    'main purpose "p"\nmain invariant "i"\n'
    "main let seed immutable Int64 21\n"
    "main let fn immutable Int64Endo double\n"
    "main let okCode immutable ExitCode 0\n"
    "main do applyFn\nmain return okCode\n"
    "ExitCode is alias\nExitCode for Int32\n"
)


def test_indirect_call_arity_mismatch_rejected():
    # WS1-057 / §33.10: an indirect call must match its operationType arity.
    src = _OPTYPE_BASE + (
        "applyFn is call\napplyFn in main\napplyFn invokes fn\n"
        "applyFn arg a Int64 seed\napplyFn arg b Int64 seed\napplyFn out answer Int64\n"
    )
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(src)
    assert getattr(exc.value, "code", None) == "SS3390"


def test_indirect_call_type_mismatch_rejected():
    src = _OPTYPE_BASE + (
        "applyFn is call\napplyFn in main\napplyFn invokes fn\n"
        "applyFn arg a Bool seed\napplyFn out answer Int64\n"
    )
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(src)
    assert getattr(exc.value, "code", None) == "SS3391"


def test_operation_reference_shadow_warns():
    # WS1-057: a binding named like a module operation warns to rename.
    src = (
        "Int64Endo is operationType\nInt64Endo in Int64\nInt64Endo out Int64\n"
        "double is operation\ndouble in n Int64\ndouble out Int64\n"
        "double let r immutable Int64 0\ndouble return r\n"
        "main is operation\nmain out ExitCode\nmain async no\n"
        'main purpose "p"\nmain invariant "i"\n'
        "main let double immutable Int64Endo double\n"
        "main let okCode immutable ExitCode 0\nmain return okCode\n"
        "ExitCode is alias\nExitCode for Int32\n"
    )
    assert "SS3392" in {d.code for d in eavc.lint(eavc.parse(src))}


def test_alias_annotation_at_written_let_position_ok():
    # WS1-029 / §10: a written `let` type may annotate a base-typed binding to an
    # alias — visible, not silent coercion.
    src = (
        "ExitCode is alias\nExitCode for Int32\n"
        "main is operation\nmain out ExitCode\nmain async no\n"
        'main purpose "p"\nmain invariant "i"\n'
        "main let rawCount immutable Int32 0\n"
        "main let annotated immutable ExitCode rawCount\n"
        "main return annotated\n"
    )
    eavc.parse(src)  # no raise; the written ExitCode annotates the Int32 value


def test_bare_return_into_alias_requires_exact_match():
    # WS1-029: returning a base-typed binding into an alias `out` (no written type
    # at the return) is rejected.
    src = (
        "ExitCode is alias\nExitCode for Int32\n"
        "main is operation\nmain out ExitCode\nmain async no\n"
        'main purpose "p"\nmain invariant "i"\n'
        "main let rawCount immutable Int32 0\n"
        "main return rawCount\n"
    )
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(src)
    assert getattr(exc.value, "code", None) == "SS1029"


def test_bare_variant_resolves_in_type_directed_position():
    # WS1-028 / §10: a bare variant in a let initializer (type-directed) lowers to
    # its discriminant; printing it yields the repr value.
    src = (
        "P is project\nP module m\nP target console\nP entry main\n"
        'm is module\nm path a.b\nm purpose "p"\nm invariant "i"\n'
        "ExitCode is alias\nExitCode for Int32\n"
        "Status is enum\nStatus variant openState\nStatus variant doneState\n"
        "Status repr openState 0\nStatus repr doneState 1\n"
        "main is operation\nmain out ExitCode\nmain async no\n"
        'main purpose "p"\nmain invariant "i"\n'
        "main let chosen immutable Status doneState\n"
        "main let okCode immutable ExitCode 0\n"
        "main do showIt\nmain return okCode\n"
        "showIt is call\nshowIt in main\nshowIt invokes console.writeIntegerLine\n"
        "showIt arg value Int64 chosen\n"
    )
    prog = eavc.parse(src)
    assert not any(d.severity == "error" for d in eavc.lint(prog))
    ir_text = str(eavc.lower_to_llvm(prog))
    assert ir_text  # lowered without an out-of-scope error


def test_bare_variant_outside_type_directed_position_rejected():
    # WS1-028: a variant in a branch condition (a Bool position) is a hard error.
    src = (
        "Status is enum\nStatus variant openState\nStatus variant doneState\n"
        "main is operation\nmain out ExitCode\nmain async no\n"
        "main let okCode immutable ExitCode 0\n"
        "main branch if doneState goto skip\n"
        "main at skip return okCode\n"
    )
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(src)
    assert getattr(exc.value, "code", None) == "SS1028"


def _constant_program(extra_lets="", dup=False, target_uses=True):
    dup_row = "Demo constant maxRetries Int64 9\n" if dup else ""
    use = ("main do show\n" if target_uses else "")
    show = (
        "show is call\nshow in main\nshow invokes console.writeIntegerLine\n"
        "show arg value Int64 maxRetries\n" if target_uses else ""
    )
    return (
        "Demo is project\nDemo module m\nDemo target console\nDemo entry main\n"
        "Demo constant maxRetries Int64 5\n" + dup_row +
        'm is module\nm path a.b\nm purpose "p"\nm invariant "i"\nm exports main\n'
        "ExitCode is alias\nExitCode for Int32\n"
        "main is operation\nmain out ExitCode\nmain async no\n"
        'main purpose "p"\nmain invariant "i"\n' + extra_lets +
        "main let okCode immutable ExitCode 0\n" + use + "main return okCode\n" + show
    )


def test_project_constant_bare_read_jit_runs():
    # WS3-041: a project constant is readable by bare name (project-global) and
    # lowers to its build value.
    proc = subprocess.run(
        [sys.executable, os.path.join(HERE, "eavc.py"), "run", "-"],
        input=_constant_program(), capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "5"


def test_project_constant_local_shadow_rejected():
    # WS3-041: a local binding may not shadow a project constant.
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(_constant_program(
            extra_lets="main let maxRetries immutable Int64 0\n", target_uses=False))
    assert getattr(exc.value, "code", None) == "SS3041D"


def test_project_constant_collision_rejected():
    # WS3-041: two constants with the same name collide.
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(_constant_program(dup=True, target_uses=False))
    assert getattr(exc.value, "code", None) == "SS3041C"


def _propagate_program(worker_err):
    return (
        "LookupError is error\nLookupError purpose \"p\"\n"
        "LookupFailed is errorCase\nLookupFailed of LookupError\n"
        "OtherError is error\nOtherError purpose \"p\"\n"
        "OtherFailed is errorCase\nOtherFailed of OtherError\n"
        "doLookup is operation\ndoLookup out Result Int64 LookupError\n"
        'doLookup async no\ndoLookup purpose "p"\ndoLookup invariant "i"\n'
        "doLookup let okVal immutable Int64 0\n"
        "doLookup do openH\ndoLookup defer hCleanup\ndoLookup return okVal nil\n"
        "openH is call\nopenH in doLookup\nopenH invokes res.open\n"
        "openH out handle Int64\nopenH owns handle\nopenH cleanedBy hCleanup\n"
        "closeH is call\ncloseH in doLookup\ncloseH invokes res.close\n"
        f"closeH arg h Int64 handle\ncloseH catch closeErr {worker_err}\n"
        "hCleanup is cleanup\nhCleanup in doLookup\nhCleanup call closeH\n"
        'hCleanup onFailure propagate\nhCleanup because "release"\nhCleanup cleans handle\n'
    )


def test_propagate_matching_error_type_ok():
    # WS2-053: under replace semantics, a propagated error matching the op's
    # Result error slot is accepted.
    eavc.parse(_propagate_program("LookupError"))


def test_propagate_error_type_mismatch_rejected():
    # WS2-053: a propagated error that doesn't fit the Result error slot is
    # rejected (replace semantics — the propagated error becomes the op's error).
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(_propagate_program("OtherError"))
    assert getattr(exc.value, "code", None) == "SS1519"


def _owned_program(violation="", ret="main return okCode\n", out_type="ExitCode"):
    return (
        "P is project\nP module m\nP target console\nP entry main\n"
        'm is module\nm path a.b\nm purpose "p"\nm invariant "i"\nm exports main\n'
        "ExitCode is alias\nExitCode for Int32\n"
        "Handle is alias\nHandle for OpaquePointer\n"
        f"main is operation\nmain out {out_type}\nmain async no\n"
        'main purpose "p"\nmain invariant "i"\n'
        "main let okCode immutable ExitCode 0\n"
        "main do openH\nmain defer hCleanup\n" + violation + ret +
        "openH is call\nopenH in main\nopenH invokes res.open\n"
        "openH out handle Handle\nopenH owns handle\nopenH cleanedBy hCleanup\n"
        "closeH is call\ncloseH in main\ncloseH invokes res.close\n"
        'closeH arg h Handle handle\ncloseH discards "close"\n'
        "hCleanup is cleanup\nhCleanup in main\nhCleanup call closeH\n"
        'hCleanup because "release"\nhCleanup cleans handle\n'
    )


def test_owned_handle_valid_ownership_ok():
    eavc.parse(_owned_program())  # no raise


def test_owned_handle_alias_rejected():
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(_owned_program(violation="main let aliasHandle immutable Handle handle\n"))
    assert getattr(exc.value, "code", None) == "SS3044A"


def test_owned_handle_double_cleanup_rejected():
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(_owned_program(violation="main defer hCleanup\n"))
    assert getattr(exc.value, "code", None) == "SS3044B"


def test_owned_handle_escape_via_return_rejected():
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(_owned_program(ret="main return handle\n", out_type="Handle"))
    assert getattr(exc.value, "code", None) == "SS3044C"


def test_island_body_kind_type_mismatch_rejected():
    # WS3-024: a body kind must match the entity's declared type.
    src = "q is storage\nq type SqlText\nq body json\n    {\"a\": 1}\n"
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(src)
    assert getattr(exc.value, "code", None) == "SS3024"


def test_island_malformed_json_rejected():
    # WS3-024: a json island must be valid JSON.
    src = "cfg is storage\ncfg type JsonText\ncfg body json\n    {oops not json\n"
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(src)
    assert getattr(exc.value, "code", None) == "SS3024J"


def test_island_sql_placeholder_count_mismatch_rejected():
    # WS3-024: a sql island's `?` count must equal the call's parameter args.
    src = (
        "P is project\nP module m\nP target console\nP entry main\n"
        'm is module\nm path a.b\nm purpose "p"\nm invariant "i"\nm exports main\n'
        "ExitCode is alias\nExitCode for Int32\n"
        "lookupSql is storage\nlookupSql scope module\nlookupSql type SqlText\n"
        "lookupSql mutability immutable\nlookupSql body sql\n"
        "    SELECT x FROM t WHERE a = ? AND b = ?\n"
        "main is operation\nmain out ExitCode\nmain async no\n"
        'main purpose "p"\nmain invariant "i"\n'
        "main let db immutable Int64 0\nmain let firstParam immutable Int64 1\n"
        "main let okCode immutable ExitCode 0\nmain do runQuery\nmain return okCode\n"
        "runQuery is call\nrunQuery in main\nrunQuery invokes sqlite.prepareStatement\n"
        "runQuery arg database Int64 db\nrunQuery arg sql SqlText lookupSql\n"
        "runQuery arg firstParam Int64 firstParam\nrunQuery out stmt Int64\n"
    )
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(src)
    assert getattr(exc.value, "code", None) == "SS3024Q"


_HTML_TRUST_BASE = (
    "Demo is project\nDemo module m\nDemo target console\nDemo entry main\n"
    'm is module\nm path a.b\nm purpose "p"\nm invariant "i"\nm exports main\n'
    "ExitCode is alias\nExitCode for Int32\n"
    "HtmlFragment is alias\nHtmlFragment for String\n"
    "HtmlTrustedFragment is alias\nHtmlTrustedFragment for String\n"
    "main is operation\nmain out ExitCode\nmain async no\n"
    'main purpose "p"\nmain invariant "i"\n'
    'main let raw immutable String "<b>x</b>"\nmain let okCode immutable ExitCode 0\n'
    "main do mint\nmain return okCode\n"
)


def test_html_trusted_fragment_off_boundary_rejected():
    # WS3-025: only html.trustFragment may mint an HtmlTrustedFragment.
    src = _HTML_TRUST_BASE + (
        "mint is call\nmint in main\nmint invokes html.escapeText\n"
        "mint arg text String raw\nmint out frag HtmlTrustedFragment\n"
    )
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(src)
    assert getattr(exc.value, "code", None) == "SS3025"


def test_html_trusted_fragment_via_boundary_ok():
    src = _HTML_TRUST_BASE + (
        "mint is call\nmint in main\nmint invokes html.trustFragment\n"
        "mint arg raw String raw\nmint out frag HtmlTrustedFragment\n"
    )
    eavc.parse(src)  # no raise


def test_html_fragment_newtypes_not_interchangeable():
    # WS3-025 / §10: passing an HtmlFragment where an HtmlTrustedFragment user-op
    # input is declared is the no-coercion newtype error (SS3710).
    src = (
        "HtmlFragment is alias\nHtmlFragment for String\n"
        "HtmlTrustedFragment is alias\nHtmlTrustedFragment for String\n"
        "renderTrusted is operation\nrenderTrusted in fragment HtmlTrustedFragment\n"
        "renderTrusted out Int32\nrenderTrusted let r immutable Int32 0\n"
        "renderTrusted return r\n"
        "main is operation\nmain out ExitCode\nmain async no\n"
        'main purpose "p"\nmain invariant "i"\n'
        'main let escaped immutable HtmlFragment "<b>x</b>"\n'
        'main let okCode immutable ExitCode 0\nmain do callRender\nmain return okCode\n'
        "callRender is call\ncallRender in main\ncallRender invokes renderTrusted\n"
        "callRender discards \"demo\"\ncallRender arg fragment HtmlFragment escaped\n"
        "ExitCode is alias\nExitCode for Int32\n"
    )
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(src)
    assert getattr(exc.value, "code", None) == "SS3710"


def _webserver_program(route_row, handler_block):
    return (
        "Demo is project\nDemo module m\nDemo target webServer\n"
        'm is module\nm path a.b\nm purpose "p"\nm invariant "i"\n'
        "ExitCode is alias\nExitCode for Int32\n"
        "HttpRequest is alias\nHttpRequest for OpaquePointer\n"
        "HttpResponse is alias\nHttpResponse for OpaquePointer\n"
        "NextMiddleware is alias\nNextMiddleware for OpaquePointer\n"
        "api is webServer\napi host home\napi port 8080\n" + route_row +
        handler_block
    )


_OK_HANDLER = (
    "healthHandler is operation\nhealthHandler in request HttpRequest\n"
    "healthHandler in response HttpResponse\nhealthHandler out Int32\n"
    'healthHandler async no\nhealthHandler purpose "p"\nhealthHandler invariant "i"\n'
    "healthHandler let okStatus immutable Int32 200\nhealthHandler return okStatus\n"
)


def test_webserver_valid_handler_abi_ok():
    eavc.parse(_webserver_program("api route GET /health healthHandler\n", _OK_HANDLER))


def test_webserver_bad_method_rejected():
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(_webserver_program("api route FETCH /health healthHandler\n", _OK_HANDLER))
    assert getattr(exc.value, "code", None) == "SS2601"


def test_webserver_dynamic_route_accepted():
    # §14 dynamic routing (user-approved reversal of the v0.3 static-only rule):
    # a `:id` route parameter now lints clean; a malformed `:` segment is SS2602.
    prog = eavc.parse(_webserver_program("api route GET /users/:id healthHandler\n", _OK_HANDLER))
    assert not [d.render() for d in eavc.lint(prog) if d.severity == "error"]
    with pytest.raises(eavc.EavError) as exc:
        eavc.lint(eavc.parse(_webserver_program("api route GET /users/: healthHandler\n", _OK_HANDLER)))
    assert getattr(exc.value, "code", None) == "SS2602"


def test_webserver_handler_abi_mismatch_rejected():
    # out Bool instead of Int32 for a route handler
    bad = (
        "healthHandler is operation\nhealthHandler in request HttpRequest\n"
        "healthHandler in response HttpResponse\nhealthHandler out Bool\n"
        'healthHandler async no\nhealthHandler purpose "p"\nhealthHandler invariant "i"\n'
        "healthHandler let okFlag immutable Bool true\nhealthHandler return okFlag\n"
    )
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(_webserver_program("api route GET /health healthHandler\n", bad))
    assert getattr(exc.value, "code", None) == "SS2603"


def test_metadata_payload_shapes():
    # WS2-035 / §6: free-text metadata is quoted; identifier metadata is bare.
    def codes(extra):
        src = (
            "Thing is record\nThing field a Int64\n" + extra
        )
        return {d.code for d in eavc.lint(eavc.parse(src))}
    assert "MD1042" in codes("Thing purpose bare\n")        # purpose unquoted
    assert "MD1043" in codes('Thing purpose "ok"\nThing invariant bare\n')
    assert "MD1045" in codes('Thing purpose "ok"\nThing deprecated bare\n')
    assert "MD1044" in codes('Thing purpose "ok"\nThing tag "quoted"\n')
    assert "MD1047" in codes('Thing purpose "ok"\nThing owner "quoted"\n')
    # well-formed metadata produces none of these
    ok = codes('Thing purpose "ok"\nThing invariant "ok"\nThing tag fast\nThing owner team\n')
    assert not ({"MD1042", "MD1043", "MD1044", "MD1045", "MD1047"} & ok)


def _configure_program(gate=""):
    return (
        "Demo is project\nDemo module m\nDemo target console\nDemo entry main\n"
        "Demo configure setupBuild\n"
        'm is module\nm path a.b\nm purpose "p"\nm invariant "i"\nm exports main\n'
        "ExitCode is alias\nExitCode for Int32\n"
        "setupBuild is operation\nsetupBuild out ExitCode\nsetupBuild async no\n"
        'setupBuild purpose "p"\nsetupBuild invariant "i"\n' + gate +
        "setupBuild let okCode immutable ExitCode 0\nsetupBuild return okCode\n"
        "main is operation\nmain out ExitCode\nmain async no\n"
        'main purpose "p"\nmain invariant "i"\nmain let okCode immutable ExitCode 0\n'
        "main return okCode\n"
    )


def test_ungated_configure_ok():
    eavc.parse(_configure_program())  # no raise


def test_gated_configure_rejected():
    # WS3-043: a configure op runs once, ungated — a forTarget gate is an error.
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(_configure_program(gate="setupBuild forTarget console\n"))
    assert getattr(exc.value, "code", None) == "SS3043"


def _platform_override_program(name="maxRetries", value="9"):
    return (
        "Demo is project\nDemo module m\nDemo target console\nDemo entry main\n"
        "Demo constant maxRetries Int64 5\nDemo platform linuxX64\n"
        'm is module\nm path a.b\nm purpose "p"\nm invariant "i"\nm exports main\n'
        "ExitCode is alias\nExitCode for Int32\n"
        "linuxX64 is platform\nlinuxX64 os linux\nlinuxX64 arch x64\n"
        "linuxX64 targetRuntime native\n"
        f"linuxX64 override {name} {value}\n"
        "main is operation\nmain out ExitCode\nmain async no\n"
        'main purpose "p"\nmain invariant "i"\nmain let okCode immutable ExitCode 0\n'
        "main return okCode\n"
    )


def test_platform_override_valid_applies():
    eavc.parse(_platform_override_program())  # no raise


def test_platform_override_unknown_constant_rejected():
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(_platform_override_program(name="nope"))
    assert getattr(exc.value, "code", None) == "SS3042A"


def test_platform_override_type_mismatch_rejected():
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(_platform_override_program(value="true"))
    assert getattr(exc.value, "code", None) == "SS3042B"


def test_windows_gui_target_reserved_error():
    # WS3-044 / X-045: `target windowsGui` is a hard reserved-target error.
    src = (
        "GuiApp is project\nGuiApp module m\nGuiApp target windowsGui\nGuiApp entry main\n"
        'm is module\nm path a.b\nm purpose "p"\nm invariant "i"\n'
        "main is operation\nmain out ExitCode\nmain async no\n"
        'main purpose "p"\nmain invariant "i"\nmain let okCode immutable ExitCode 0\n'
        "main return okCode\nExitCode is alias\nExitCode for Int32\n"
    )
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(src)
    assert getattr(exc.value, "code", None) == "SS0744"


@pytest.mark.skipif(not _have_c_compiler(), reason="no C compiler for the runtime lane")
def test_runtime_native_symbol_lane():
    # X-061: the runtimeBinding native-symbol lane — discover compiler, select the
    # manifest lib for a program's symbols, build it, and register the symbols.
    assert eavc._find_c_compiler() is not None
    sqlite_stub = (
        "standardSqlite is module\nstandardSqlite path standard.sqlite\n"
        'standardSqlite purpose "p"\nstandardSqlite invariant "i"\n'
        "openInMemory is operation\nopenInMemory out OpaquePointer\n"
        "openInMemory body runtimeBinding eav_sqlite_open_memory\n"
        'openInMemory purpose "open"\n'
    )
    prog = eavc.parse(sqlite_stub)
    assert eavc._referenced_runtime_symbols(prog) == {"eav_sqlite_open_memory"}
    libs = eavc._runtime_libs_for(prog)
    assert [lib["name"] for lib in libs] == ["eav_runtime"]
    path = eavc._ensure_runtime_lib(libs[0])
    assert path and os.path.exists(path)
    # registration resolves the symbol into the JIT without raising
    eavc._ensure_native_init()
    eavc._register_runtime_symbols(prog)
    # a program with no runtimeBinding selects no runtime libs
    plain = eavc.parse(open(os.path.join(EXAMPLES, "hello_world.sem"), encoding="utf-8").read())
    assert eavc._runtime_libs_for(plain) == []


def test_cli_subcommands_in_process(tmp_path, capsys):
    # X-060: drive each cmd_* through main() in-process (not just subprocess), so
    # the CLI dispatch surface is covered. Each invocation returns 0.
    src_path = os.path.join(EXAMPLES, "hello_world.sem")
    exe = str(tmp_path / ("h" + (".exe" if sys.platform == "win32" else "")))
    invocations = [
        ["lex", src_path], ["parse", src_path], ["lower", src_path],
        ["run", src_path], ["fmt", src_path], ["fmt", "--surface", "compact", src_path],
        ["lint", src_path], ["normalize", src_path], ["inventory", src_path],
        ["verify-patch", src_path], ["explain", "SS1502"],
        ["query", "effects", src_path], ["trace", src_path, "main"],
        ["scaffold", "console-program"], ["graph", src_path],
        ["slice", src_path, "main"], ["describe", src_path, "main"],
        ["build", src_path, "-o", exe],
    ]
    for argv in invocations:
        rc = eavc.main(argv)
        assert rc == 0, (argv, capsys.readouterr())


def _test_program(test_ops):
    base = (
        "P is project\nP module m\nP target console\nP entry main\n"
        'm is module\nm path a.b\nm purpose "p"\nm invariant "i"\nm exports main\n'
        "ExitCode is alias\nExitCode for Int32\n"
        "main is operation\nmain out ExitCode\nmain async no\n"
        'main purpose "p"\nmain invariant "i"\nmain let okCode immutable ExitCode 0\n'
        "main return okCode\n"
    )
    return base + test_ops


def test_test_runner_executes_tag_test_ops():
    # WS3-026/WS4-119: each `tag test` op is JIT-run; exit 0 = pass.
    passing = (
        "checkAddsUp is operation\ncheckAddsUp out ExitCode\ncheckAddsUp async no\n"
        'checkAddsUp tag test\ncheckAddsUp purpose "p"\ncheckAddsUp invariant "i"\n'
        "checkAddsUp let pass immutable ExitCode 0\ncheckAddsUp return pass\n"
    )
    report = eavc.run_tests(eavc.parse(_test_program(passing)))
    assert report["preflightStatus"] == "ok"
    assert report["compositeStatus"] == "pass"
    assert [t["name"] for t in report["tests"]] == ["checkAddsUp"]
    assert report["tests"][0]["status"] == "pass"
    # a failing test (nonzero exit) flips composite to fail
    failing = passing + (
        "checkFails is operation\ncheckFails out ExitCode\ncheckFails async no\n"
        'checkFails tag test\ncheckFails purpose "p"\ncheckFails invariant "i"\n'
        "checkFails let fail immutable ExitCode 1\ncheckFails return fail\n"
    )
    rep2 = eavc.run_tests(eavc.parse(_test_program(failing)))
    assert rep2["compositeStatus"] == "fail"
    assert {t["name"]: t["status"] for t in rep2["tests"]}["checkFails"] == "fail"


def test_agent_operating_loop(tmp_path, capsys):
    # WS4-122: the documented loop — check, then follow its replayable
    # nextCommands (test/build) to a runnable artifact.
    import json
    path = os.path.join(EXAMPLES, "hello_world.sem")
    eavc.main(["check", path])
    chk = json.loads(capsys.readouterr().out)
    assert chk["status"] in ("ok", "ok-with-warnings")
    for nc in chk["nextCommands"]:
        assert nc["replayable"] is True
        argv = list(nc["argv"])
        if argv[0] == "build":
            argv = ["build", path, "-o", str(tmp_path / ("h" + (".exe" if sys.platform == "win32" else "")))]
        rc = eavc.main(argv)
        capsys.readouterr()
        assert rc == 0, argv


def test_entity_scoped_slice_json(capsys):
    # WS4-121: entity-scoped slice as a first-class sem.slice.v1 envelope.
    import json
    eavc.main(["slice", os.path.join(EXAMPLES, "hello_world.sem"), "main", "--json"])
    env = json.loads(capsys.readouterr().out)
    assert env["surface"] == "sem.slice.v1"
    assert env["entity"] == "main" and env["kind"] == "operation"
    assert env["slice"]


_HTML_RENDER_SRC = (
    "P is project\nP module m\nP target console\nP entry main\n"
    'm is module\nm path a.b\nm purpose "p"\nm invariant "i"\nm exports main\n'
    "ExitCode is alias\nExitCode for Int32\n"
    "PageTemplate is htmlTemplate\nPageTemplate body html\n"
    "    <h1>{{title}}</h1><p>{{body}}</p>\n"
    "main is operation\nmain out ExitCode\nmain async no\n"
    'main purpose "p"\nmain invariant "i"\n'
    'main let titleText immutable String "Hi <b>x</b>"\n'
    'main let bodyText immutable String "A & B"\n'
    "main let okCode immutable ExitCode 0\n"
    "main do renderPage\nmain do showPage\nmain return okCode\n"
    "renderPage is call\nrenderPage in main\nrenderPage invokes html.render\n"
    "renderPage arg template HtmlTemplate PageTemplate\n"
    "renderPage arg title String titleText\nrenderPage arg body String bodyText\n"
    "renderPage out pageHtml String\n"
    "showPage is call\nshowPage in main\nshowPage invokes console.writeLine\n"
    "showPage arg text String pageHtml\n"
)


_HTTP_SERVER_MAIN = """
HttpServerDemo is project
HttpServerDemo module appHttpServer
HttpServerDemo target console
HttpServerDemo entry main

appHttpServer is module
appHttpServer path apps.httpServer
appHttpServer exports main
appHttpServer purpose "Serve one route with a handler"
appHttpServer invariant "Routes GET /health to healthHandler"

ExitCode is alias
ExitCode for Int32

healthHandler is operation
healthHandler in request OpaquePointer
healthHandler in response OpaquePointer
healthHandler out Int32
healthHandler async no
healthHandler purpose "Respond 200 ok to a health probe"
healthHandler invariant "Writes a 200 plaintext response"
healthHandler let okStatus immutable Int32 200
healthHandler let bodyText immutable String "ok"
healthHandler let continueCode immutable Int32 0
healthHandler do sendResponse
healthHandler return continueCode

sendResponse is call
sendResponse in healthHandler
sendResponse invokes respond
sendResponse arg response OpaquePointer response
sendResponse arg status Int32 okStatus
sendResponse arg body String bodyText
sendResponse discards "runtime status"

main is operation
main out ExitCode
main async no
main purpose "Run the HTTP server on /health"
main invariant "Serves until shutdown"
main let host immutable String "127.0.0.1"
main let port immutable Int32 8080
main let getMethod immutable String "GET"
main let healthPath immutable String "/health"
main let handlerRef immutable HttpHandler healthHandler
main let okCode immutable ExitCode 0
main do startServer
main return okCode

startServer is call
startServer in main
startServer invokes serve
startServer arg host String host
startServer arg port Int32 port
startServer arg method String getMethod
startServer arg path String healthPath
startServer arg handler HttpHandler handlerRef
startServer discards "server exit status"
"""


@pytest.mark.skipif(not _have_c_compiler(), reason="no C compiler to link the server")
def test_http_server_links_into_exe(tmp_path):
    # WS3-017: the blocking HTTP server (ss_http_server_run) + a handler/response
    # wire through the runtimeBinding seam and link into a native exe (the live
    # blocking serve is signal-shutdown-driven, run from a real process).
    stdlib = open(os.path.join(STD, "standard.http.sem"), encoding="utf-8").read()
    program = eavc.parse(stdlib + "\n" + _HTTP_SERVER_MAIN)
    assert not any(d.severity == "error" for d in eavc.lint(program))
    ir = str(eavc.lower_to_llvm(program))
    assert "eav_http_serve" in ir and "eav_http_respond" in ir
    out = str(tmp_path / ("server" + (".exe" if sys.platform == "win32" else "")))
    eavc.build_executable(program, out)
    assert os.path.exists(out)


_SET_STEP_SRC = """
SetDemo is project
SetDemo module examplesSetDemo
SetDemo target console
SetDemo entry main

examplesSetDemo is module
examplesSetDemo path examples.setDemo
examplesSetDemo exports main
examplesSetDemo purpose "Assign a mutable local to literals across a branch"
examplesSetDemo invariant "Prints 42 — the value set on the taken branch"

ExitCode is alias
ExitCode for Int32

answerSlot is storage
answerSlot scope module
answerSlot type Int64
answerSlot mutability mutable
answerSlot purpose "A module-mutable slot assigned by set"

stdoutWriter is capability
stdoutWriter grants write console.stdout
stdoutWriter purpose "Allow controlled writes to standard output"

slotWriter is capability
slotWriter grants write storage.answerSlot
slotWriter purpose "Allow mutation of answerSlot"

main is operation
main out ExitCode
main effect write console.stdout
main effect write storage.answerSlot
main uses stdoutWriter
main uses slotWriter
main memory heap no
main async no
main purpose "set a mutable local to a literal, branch, set it again, print it"
main invariant "Prints 42"
main let chosen mutable Int64 0
main let useBig immutable Bool true
main let okCode immutable ExitCode 0
main set chosen 7
main branch if useBig goto bigValue
main do printChosen
main return okCode
main at bigValue set chosen 42
main set answerSlot chosen
main do printSlot
main return okCode

printChosen is call
printChosen in main
printChosen invokes console.writeIntegerLine
printChosen arg value Int64 chosen

printSlot is call
printSlot in main
printSlot invokes console.writeIntegerLine
printSlot arg value Int64 answerSlot
"""


def test_set_step_assigns_mutable_and_runs():
    # §12 set step (user-chosen language feature): `set NAME VALUE` assigns a
    # mutable local or module storage to a literal/binding (no producing call).
    # Prints 42 — a no-op `set` would leave `chosen` at 0 and print 0.
    prog = eavc.parse(_SET_STEP_SRC)
    assert not [d.render() for d in eavc.lint(prog) if d.severity == "error"]
    ir = str(eavc.lower_to_llvm(prog))
    assert "store" in ir
    proc = subprocess.run(
        [sys.executable, os.path.join(HERE, "eavc.py"), "run", "-"],
        input=_SET_STEP_SRC, capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "42"


_INLINE_STORAGE_SRC = """
InlineStorage is project
InlineStorage module examplesInlineStorage
InlineStorage target console
InlineStorage entry main

examplesInlineStorage is module
examplesInlineStorage path examples.inlineStorage
examplesInlineStorage exports main
examplesInlineStorage purpose "Declare a module constant in one line and print it"
examplesInlineStorage invariant "Prints 7 — the single-line storage value"

ExitCode is alias
ExitCode for Int32

answerConstant is storage module immutable Int64 7

stdoutWriter is capability
stdoutWriter grants write console.stdout
stdoutWriter purpose "Allow controlled writes to standard output"

main is operation
main out ExitCode
main effect write console.stdout
main uses stdoutWriter
main memory heap no
main async no
main purpose "Print the single-line module constant"
main invariant "Writes exactly one integer line: 7"
main let okCode immutable ExitCode 0
main do writeIt
main return okCode

writeIt is call
writeIt in main
writeIt invokes console.writeIntegerLine
writeIt arg value Int64 answerConstant
"""


def test_inline_storage_declaration_runs():
    # §12 single-line module-storage form: `NAME is storage <scope> <mutability>
    # <type> <value>` populates scope/mutability/type/value in one row, like the
    # one-line `let`. Prints 7 — if the inline tokens were dropped the global
    # would default to 0 and print 0.
    prog = eavc.parse(_INLINE_STORAGE_SRC)
    st = prog.entities["answerConstant"]
    assert [r.payload[0] for r in st.facts("scope")] == ["module"]
    assert [r.payload[0] for r in st.facts("type")] == ["Int64"]
    assert [r.payload[0] for r in st.facts("value")] == ["7"]
    assert not [d.render() for d in eavc.lint(prog) if d.severity == "error"]
    proc = subprocess.run(
        [sys.executable, os.path.join(HERE, "eavc.py"), "run", "-"],
        input=_INLINE_STORAGE_SRC, capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "7"


def test_set_step_on_immutable_rejected():
    # §12: `set` on an immutable let (or unknown name) is SS1087.
    src = _SET_STEP_SRC.replace("main let chosen mutable Int64 0",
                                "main let chosen immutable Int64 0")
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(src)
    assert getattr(exc.value, "code", None) == "SS1087"


def test_html_render_full_document():
    # X-011: html.render renders the full htmlTemplate document, auto-escaping
    # text holes (not a single string.concat line).
    assert not any(d.severity == "error" for d in eavc.lint(eavc.parse(_HTML_RENDER_SRC)))
    ir = str(eavc.lower_to_llvm(eavc.parse(_HTML_RENDER_SRC)))
    assert "eav_http_html_escape" in ir  # holes are auto-escaped
    proc = subprocess.run(
        [sys.executable, os.path.join(HERE, "eavc.py"), "run", "-"],
        input=_HTML_RENDER_SRC, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "<h1>Hi &lt;b&gt;x&lt;/b&gt;</h1><p>A &amp; B</p>"


_FRAGMENT_NEST_SRC = (
    "FragNest is project\nFragNest module appFragNest\n"
    "FragNest target console\nFragNest entry main\n"
    "appFragNest is module\nappFragNest path a.b\n"
    'appFragNest purpose "p"\nappFragNest invariant "i"\n'
    "ExitCode is alias\nExitCode for Int32\n"
    "HtmlFragment is alias\nHtmlFragment for String\n"
    "HtmlTemplate is alias\nHtmlTemplate for String\n"
    "inner is htmlTemplate\ninner body html\n  <b>{{name}}</b>\n\n"
    "outer is htmlTemplate\nouter body html\n  <div>{{frag}}</div><p>{{text}}</p>\n\n"
    "main is operation\nmain out ExitCode\nmain async no\n"
    'main purpose "p"\nmain invariant "i"\n'
    'main let name immutable String "x"\nmain let text immutable String "a<i>b"\n'
    "main let okCode immutable ExitCode 0\n"
    "main do renderInner\nmain do renderOuter\nmain do show\nmain return okCode\n"
    "renderInner is call\nrenderInner in main\nrenderInner invokes html.render\n"
    "renderInner arg template HtmlTemplate inner\nrenderInner arg name String name\n"
    "renderInner out frag HtmlFragment\n"
    "renderOuter is call\nrenderOuter in main\nrenderOuter invokes html.render\n"
    "renderOuter arg template HtmlTemplate outer\n"
    "renderOuter arg frag HtmlFragment frag\nrenderOuter arg text String text\n"
    "renderOuter out doc String\n"
    "show is call\nshow in main\nshow invokes console.writeLine\nshow arg text String doc\n"
)


def test_html_render_fragment_hole_inserted_raw():
    # README ss16 §10: an HtmlFragment hole is already-escaped/trusted markup, so
    # html.render nests it RAW; only plain String holes are escaped. No-op-failing:
    # the prior lowering escaped every non-HtmlSafeUrl hole, double-escaping the
    # nested fragment.
    assert not any(d.severity == "error" for d in eavc.lint(eavc.parse(_FRAGMENT_NEST_SRC)))
    proc = subprocess.run(
        [sys.executable, os.path.join(HERE, "eavc.py"), "run", "-"],
        input=_FRAGMENT_NEST_SRC, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    # the fragment is nested raw; the sibling String hole is still escaped
    assert proc.stdout.strip() == "<div><b>x</b></div><p>a&lt;i&gt;b</p>"


_CONST_ALIAS_SRC = (
    "Alias is project\nAlias module appAlias\n"
    "Alias target console\nAlias entry main\n"
    "appAlias is module\nappAlias path a.b\n"
    'appAlias purpose "p"\nappAlias invariant "i"\n'
    "ExitCode is alias\nExitCode for Int32\n"
    'doneClass is storage module immutable String "todo-row todo-row-done"\n'
    "firstClass is storage module immutable String doneClass\n"
    "main is operation\nmain out ExitCode\nmain async no\n"
    'main purpose "p"\nmain invariant "i"\n'
    "main let okCode immutable ExitCode 0\n"
    "main do show\nmain return okCode\n"
    "show is call\nshow in main\nshow invokes console.writeLine\nshow arg text String firstClass\n"
)


def test_cross_module_storage_initializer_resolves():
    # README ss12: a module constant may alias another constant's value
    # (firstClass <- doneClass). No-op-failing: codegen previously required a
    # literal and raised on the reference token.
    assert not any(d.severity == "error" for d in eavc.lint(eavc.parse(_CONST_ALIAS_SRC)))
    proc = subprocess.run(
        [sys.executable, os.path.join(HERE, "eavc.py"), "run", "-"],
        input=_CONST_ALIAS_SRC, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "todo-row todo-row-done"


def test_frozen_executable_packaging():
    # X-025: the packager exists and eavc is frozen-path-aware; if a built exe is
    # present (dist/eavc[.exe] from `python package.py`), it runs standalone.
    assert os.path.exists(os.path.join(HERE, "package.py"))
    assert hasattr(eavc, "_bundle_dir")
    exe = os.path.join(HERE, "dist", "eavc" + (".exe" if sys.platform == "win32" else ""))
    if not os.path.exists(exe):
        pytest.skip("standalone exe not built (run `python package.py`)")
    ver = subprocess.run([exe, "version", "--json"], capture_output=True, text=True)
    assert ver.returncode == 0 and eavc.CONTRACT_VERSION in ver.stdout
    run = subprocess.run([exe, "run", os.path.join(EXAMPLES, "hello_world.sem")],
                         capture_output=True, text=True)
    assert run.returncode == 0 and "hello world" in run.stdout


def test_golden_match_infra(tmp_path):
    # X-007: matchesGolden compares to a committed golden + verifies sha256;
    # mismatch fails (no implicit update); --update-golden re-pins.
    import hashlib
    g = tmp_path / "out.golden"
    # create the golden via update, capture its pinned digest
    created = eavc.golden_match("expected\n", str(g), update=True)
    assert created["ok"] is True
    digest = created["digest"]
    assert digest == hashlib.sha256(b"expected\n").hexdigest()
    # matching output + correct digest passes
    assert eavc.golden_match("expected\n", str(g), expected_digest=digest)["ok"]
    # tampered output fails (content mismatch), golden not rewritten
    bad = eavc.golden_match("tampered\n", str(g), expected_digest=digest)
    assert bad["ok"] is False and bad["contentMatch"] is False
    assert g.read_text(encoding="utf-8") == "expected\n"
    # a wrong expected digest fails even with matching content
    assert eavc.golden_match("expected\n", str(g), expected_digest="deadbeef")["ok"] is False
    # missing golden fails cleanly
    assert eavc.golden_match("x", str(tmp_path / "nope.golden"))["reason"] == "missing-golden"


def test_capability_injection_seam():
    # WS3-006: the capability is the test-double seam — an op declares `uses CAP`,
    # and a substitute capability granting the same effect keeps it covered;
    # nondeterministic inputs (clock/random) are modeled as capabilities.
    def prog(cap_name):
        return (
            f"{cap_name} is capability\n{cap_name} grants write console.stdout\n"
            f'{cap_name} purpose "writer"\n'
            "emit is operation\nemit out ExitCode\nemit effect write console.stdout\n"
            f"emit uses {cap_name}\nemit async no\n"
            'emit purpose "p"\nemit invariant "i"\nemit let okCode immutable ExitCode 0\n'
            "emit return okCode\nExitCode is alias\nExitCode for Int32\n"
        )
    # real and test-double capabilities are interchangeable at the `uses` seam
    for cap in ("realStdout", "fakeStdoutForTests"):
        assert not any(w for w in eavc.parse(prog(cap)).warnings if "not covered" in w)
    # nondeterministic inputs are capability-mediated (clock read needs authority)
    clock = open(os.path.join(STD, "standard.clock.sem"), encoding="utf-8").read()
    cprog = eavc.parse(clock)
    now = cprog.entities["nowMillis"]
    assert now.fact("effect") is not None and now.fact("uses") is not None


def test_project_test_discovery_by_layout(tmp_path, capsys):
    # WS3-048: tests discovered by location — co-located src/*.test.sem + tests/.
    root = tmp_path / "proj"
    eavc.main(["new", str(root)])
    capsys.readouterr()
    (root / "tests").mkdir(exist_ok=True)
    (root / "tests" / "integration_smoke.sem").write_text("# e2e\n", encoding="utf-8")
    found = eavc.discover_project_tests(str(root))
    assert any("main.test.sem" in f for f in found["coLocated"])
    assert any("integration_smoke.sem" in f for f in found["testsDir"])


def test_app_layout_conversion_plan(tmp_path):
    # WS3-049: plan the relayout of a *flat* app into the framework layout
    # (the real apps already use the build.sem + src/ layout, §28.2).
    flat = tmp_path / "flatapp"
    flat.mkdir()
    (flat / "main.sem").write_text("X is project\n", encoding="utf-8")
    (flat / "build.sem").write_text("X is project\n", encoding="utf-8")
    plan = eavc.app_layout_plan(str(flat))
    assert plan["app"] == "flatapp" and plan["output"] == "build/"
    moves = {m["from"]: m["to"] for m in plan["moves"]}
    assert moves.get("main.sem") == os.path.join("src", "main.sem")
    assert moves.get("build.sem") == "build.sem"


def test_sem_file_family_classification():
    # WS3-045: each file role in the .sem family is recognized.
    assert eavc.classify_sem_file("/x/build.sem") == "build"
    assert eavc.classify_sem_file("/x/build.sem.lock") == "lock"
    assert eavc.classify_sem_file("/x/standard.http.semsig") == "semsig"
    assert eavc.classify_sem_file("/x/src/main.test.sem") == "test"
    assert eavc.classify_sem_file("/x/src/main.sem") == "source"
    assert eavc.classify_sem_file("/x/README.md") == "other"


def test_project_directory_resolution(tmp_path, capsys):
    # WS3-046: run/check resolve a project directory (compose src/*.sem, excluding
    # tests + build.sem) — a multi-module project composes and runs.
    root = tmp_path / "multi"
    eavc.main(["new", str(root)])
    capsys.readouterr()
    # load_project composes only the runtime source (not build.sem / *.test.sem)
    composed = eavc.load_project(str(root))
    assert "is project" in composed and "writeGreeting" in composed
    proc = subprocess.run(
        [sys.executable, os.path.join(HERE, "eavc.py"), "run", str(root)],
        capture_output=True, text=True)
    assert proc.returncode == 0 and "hello from Multi" in proc.stdout


def test_new_project_scaffold(tmp_path, capsys):
    # WS3-047: eavc new produces a tree that checks clean, runs, and tests green.
    import json
    root = tmp_path / "demoapp"
    eavc.main(["new", str(root)])
    created = json.loads(capsys.readouterr().out)
    assert created["surface"] == "sem.new.v1"
    for rel in ("build.sem", "src/main.sem", "src/main.test.sem", ".gitignore"):
        assert (root / rel).exists(), rel
    # the project (build.sem project + src/ modules) checks clean and runs
    composed = eavc.load_project(str(root))
    assert "is project" in composed and "is module" in composed  # build.sem + src/
    assert not any(d.severity == "error" for d in eavc.lint(eavc.parse(composed)))
    # src/main.sem is a pure module (the project lives in build.sem, README §28.2)
    main_src = (root / "src" / "main.sem").read_text(encoding="utf-8")
    assert "is project" not in main_src and "is module" in main_src
    proc = subprocess.run(
        [sys.executable, os.path.join(HERE, "eavc.py"), "run", str(root)],
        capture_output=True, text=True)
    assert proc.returncode == 0 and "hello from Demoapp" in proc.stdout
    # the test stub runs green
    test_src = (root / "src" / "main.test.sem").read_text(encoding="utf-8")
    report = eavc.run_tests(eavc.parse(test_src))
    assert report["compositeStatus"] == "pass"
    # build.sem parses
    eavc.parse((root / "build.sem").read_text(encoding="utf-8"))


def test_semsig_legal_entity_set():
    # WS4-006: a .semsig holds only intrinsic + referenced types (+ header).
    import glob
    legal = {"semsig", "intrinsic", "record", "enum", "alias", "error", "errorCase"}
    for path in glob.glob(os.path.join(SIGS, "*.semsig")):
        prog = eavc.load_semsig(open(path, encoding="utf-8").read())
        assert all(prog.entities[n].kind in legal for n in prog.order), path
    # an operation in a .semsig is rejected
    bad = (
        "sig is semsig\nsig version \"1.0\"\nsig generatedBy \"eavc\"\nsig describes x\n"
        "main is operation\nmain out Int64\nmain let r immutable Int64 0\nmain return r\n"
    )
    with pytest.raises(eavc.EavError):
        eavc.load_semsig(bad)


def test_task_templates(capsys):
    # WS4-025: each `task` template emits its checklist sections.
    import json
    for name in ("add-route", "add-db-query", "add-cleanup", "add-async-fanout",
                 "convert-to-eav"):
        eavc.main(["task", name])
        env = json.loads(capsys.readouterr().out)
        assert env["surface"] == "sem.task.v1" and env["template"] == name
        assert env["rowsToAdd"] and env["rowsToVerify"] and env["lintRules"]
    # an unknown template lists the available ones
    rc = eavc.main(["task", "nope"])
    bad = json.loads(capsys.readouterr().out)
    assert rc == 2 and "add-route" in bad["available"]


def test_mcp_server_handler():
    # WS4-110: MCP initialize / tools/list / tools/call over the cmd surfaces.
    import json
    init = eavc.mcp_handle({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    assert init["result"]["serverInfo"]["name"] == "eavc"
    assert init["result"]["serverInfo"]["version"] == eavc.CONTRACT_VERSION
    lst = eavc.mcp_handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    names = {t["name"] for t in lst["result"]["tools"]}
    assert {"check", "version", "fix_plan"}.issubset(names)
    call = eavc.mcp_handle({
        "jsonrpc": "2.0", "id": 3, "method": "tools/call",
        "params": {"name": "check", "arguments": {"path": os.path.join(EXAMPLES, "hello_world.sem")}}})
    text = call["result"]["content"][0]["text"]
    assert json.loads(text)["surface"] == "sem.check.v1"
    # unknown method -> JSON-RPC error
    err = eavc.mcp_handle({"jsonrpc": "2.0", "id": 4, "method": "nope"})
    assert err["error"]["code"] == -32601


def test_docs_index_get_search(capsys):
    # WS4-117: docs list / get / keyword-ranked search.
    import json
    path = os.path.join(EXAMPLES, "hello_world.sem")
    eavc.main(["docs", path])
    idx = json.loads(capsys.readouterr().out)
    assert idx["surface"] == "sem.docsIndex.v1" and idx["count"] >= 5
    eavc.main(["docs", path, "--get", "main"])
    got = json.loads(capsys.readouterr().out)
    assert got["surface"] == "sem.docs.v1" and got["entity"]["name"] == "main"
    eavc.main(["docs", path, "--search", "hello world greeting"])
    res = json.loads(capsys.readouterr().out)
    assert res["surface"] == "sem.docsSearch.v1"
    assert any(r["name"] == "main" for r in res["results"])


def test_dev_surface(capsys):
    # WS4-120: dev reports one check+runnability tick (sem.dev.v1).
    import json
    eavc.main(["dev", os.path.join(EXAMPLES, "hello_world.sem")])
    env = json.loads(capsys.readouterr().out)
    assert env["surface"] == "sem.dev.v1"
    assert env["runnable"] is True and env["target"] == "console"
    assert any(c["argv"][0] in ("run", "build") for c in env["nextCommands"])


def test_check_next_commands(tmp_path, capsys):
    # WS4-112: check carries machine-facing nextCommands with argv + replayable.
    import json
    ok_path = os.path.join(EXAMPLES, "hello_world.sem")
    eavc.main(["check", ok_path])
    env = json.loads(capsys.readouterr().out)
    assert env["nextCommands"], "ok check should suggest next steps"
    nc = env["nextCommands"][0]
    assert "argv" in nc and nc["replayable"] is True and nc["argv"][0] in ("test", "build")
    # an error source suggests `fix --plan`
    bad = tmp_path / "bad.sem"
    bad.write_text("Thing is record\nThing field new TaskId\n", encoding="utf-8")
    eavc.main(["check", str(bad)])
    benv = json.loads(capsys.readouterr().out)
    if benv["status"] == "lint-diagnostics":
        assert any(c["argv"][0] == "fix" for c in benv["nextCommands"])


def test_versioned_json_envelopes(capsys):
    # WS4-111: every JSON surface emits a consistent versioned envelope
    # {surface, version, ok}, and each surface is declared in SEM_SURFACES.
    import json
    path = os.path.join(EXAMPLES, "hello_world.sem")
    cmds = [
        ["version", "--json"], ["agent-docs", "--json"], ["skills", "--json"],
        ["check", path], ["readiness", "--json"], ["deps", path],
        ["context", path], ["symbols", path], ["size", path], ["fix", path, "--plan"],
    ]
    for argv in cmds:
        eavc.main(argv)
        env = json.loads(capsys.readouterr().out)
        assert env["version"] == "v1", argv
        assert env["surface"] in eavc.SEM_SURFACES, env["surface"]
        assert "ok" in env, argv


def test_fix_plan_and_fmt_check(tmp_path, capsys):
    # WS4-114: fix --plan emits a suggestions plan; fmt --check detects drift.
    import json
    # a program with a lint error -> fix plan lists it with its repair
    bad = tmp_path / "bad.sem"
    bad.write_text(
        "Thing is record\nThing field a Int64\nThing purpose bare\n", encoding="utf-8")
    eavc.main(["fix", str(bad), "--plan"])
    plan = json.loads(capsys.readouterr().out)
    assert plan["surface"] == "sem.fixPlan.v1" and plan["status"] == "suggestions-only"
    assert any(d["code"] == "MD1042" for d in plan["diagnostics"])
    # fmt --check: canonically-formatted source passes, drifted source fails
    canon = tmp_path / "canon.sem"
    canon.write_text(eavc.format_program(eavc.parse(
        open(os.path.join(EXAMPLES, "hello_world.sem"), encoding="utf-8").read())),
        encoding="utf-8")
    assert eavc.main(["fmt", "--check", str(canon)]) == 0
    drift = tmp_path / "drift.sem"
    drift.write_text(
        "main is operation\nmain   out   ExitCode\nExitCode is alias\nExitCode for Int32\n",
        encoding="utf-8")
    assert eavc.main(["fmt", "--check", str(drift)]) == 1


def test_deps_context_symbols_surfaces(capsys):
    # WS4-116: deps / context / symbols inspection surfaces.
    import json
    path = os.path.join(EXAMPLES, "hello_world.sem")
    eavc.main(["deps", path])
    deps = json.loads(capsys.readouterr().out)
    assert deps["surface"] == "sem.deps.v1" and "imports" in deps and "requires" in deps
    eavc.main(["context", path])
    ctx = json.loads(capsys.readouterr().out)
    assert ctx["surface"] == "sem.context.v1"
    assert ctx["entry"] == "main" and ctx["targets"] == ["console"]
    eavc.main(["symbols", path])
    sym = json.loads(capsys.readouterr().out)
    assert sym["surface"] == "sem.symbols.v1"
    names = {s["name"] for s in sym["symbols"]}
    assert {"main", "HelloWorld", "ExitCode"}.issubset(names)
    eavc.main(["size", path])
    sz = json.loads(capsys.readouterr().out)
    assert sz["surface"] == "sem.size.v1"
    assert sz["entities"] >= 5 and sz["rows"] > sz["entities"]


def test_eval_snippet_jit(tmp_path):
    # WS4-118: eval auto-wraps a snippet (no project) and JIT-runs it.
    snippet = (
        "main is operation\nmain out ExitCode\nmain async no\n"
        "main let n immutable Int64 42\nmain let okCode immutable ExitCode 0\n"
        "main do show\nmain return okCode\n"
        "show is call\nshow in main\nshow invokes console.writeIntegerLine\n"
        "show arg value Int64 n\n"
    )
    snip = tmp_path / "snip.sem"
    snip.write_text(snippet, encoding="utf-8")
    import json
    proc = subprocess.run(
        [sys.executable, os.path.join(HERE, "eavc.py"), "eval", str(snip)],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["surface"] == "sem.eval.v1"
    assert payload["ok"] is True and payload["stdoutLines"] == ["42"]


def test_check_and_readiness_lanes(capsys):
    # WS4-113: check (source lane) classifies status; readiness (environment lane).
    import json
    eavc.main(["check", os.path.join(EXAMPLES, "hello_world.sem")])
    ok = json.loads(capsys.readouterr().out)
    assert ok["surface"] == "sem.check.v1" and ok["status"] in ("ok", "ok-with-warnings")
    # readiness reports the toolchain lane
    rc = eavc.main(["readiness", "--json"])
    rd = json.loads(capsys.readouterr().out)
    assert rd["surface"] == "sem.readiness.v1"
    assert rd["ok"] == (rc == 0)
    assert "cCompiler" in rd and "llvmlite" in rd


def test_check_classifies_compiler_error(tmp_path, capsys):
    import json
    bad = tmp_path / "bad.sem"
    bad.write_text("main badpredicate x\n", encoding="utf-8")  # no `is` row first
    eavc.main(["check", str(bad)])
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "compiler-error" and out["ok"] is False


def test_bootstrap_surfaces(capsys):
    # WS4-115: version / agent-docs / skills JSON surfaces.
    import json
    eavc.main(["version", "--json"])
    v = json.loads(capsys.readouterr().out)
    assert v["surface"] == "sem.version.v1" and v["contractVersion"] == eavc.CONTRACT_VERSION
    eavc.main(["agent-docs", "--json"])
    d = json.loads(capsys.readouterr().out)
    assert d["surface"] == "sem.agentDocs.v1" and "EAV-Steps" in d["rules"]
    eavc.main(["skills"])
    s = json.loads(capsys.readouterr().out)
    assert s["surface"] == "sem.skills.v1" and len(s["skills"]) >= 3
    eavc.main(["skills", "eav-run"])
    one = json.loads(capsys.readouterr().out)
    assert [k["name"] for k in one["skills"]] == ["eav-run"]


def test_coverage_floor_probe():
    # X-068: a stdlib-`trace`-style line-coverage probe over eavc.py (no third-party
    # dep) with a floor that fails on a big regression. Parsing + linting + lowering
    # + formatting every example covers a substantial slice of the compiler.
    import glob
    eav_file = eavc.__file__
    hit = set()

    def tracer(frame, event, arg):
        if event == "line" and frame.f_code.co_filename == eav_file:
            hit.add(frame.f_lineno)
        return tracer

    old = sys.gettrace()
    sys.settrace(tracer)
    try:
        for path in glob.glob(os.path.join(EXAMPLES, "*.sem")):
            src = open(path, encoding="utf-8").read()
            prog = eavc.parse(src)
            eavc.lint(prog)
            str(eavc.lower_to_llvm(prog))
            eavc.format_program(prog)
    finally:
        sys.settrace(old)
    # Floor below the current ~1570; regressing the example workload's reach
    # (e.g. a lowering path going dark) fails the guard.
    assert len(hit) >= 1400, f"coverage floor regressed: only {len(hit)} eavc lines hit"


def test_stdlib_modules_coverage_guard():
    # WS3-107: every std/*.sem module lints clean and every operation is bodied
    # (a runtimeBinding/intrinsic body, or step rows) — no stub operations.
    import glob
    mods = sorted(glob.glob(os.path.join(STD, "*.sem")))
    assert len(mods) >= 5
    for path in mods:
        prog = eavc.parse(open(path, encoding="utf-8").read())
        assert not any(d.severity == "error" for d in eavc.lint(prog)), path
        for n in prog.order:
            op = prog.entities[n]
            if op.kind not in ("operation", "function"):
                continue
            has_body_row = op.fact("body") is not None
            has_steps = any(
                r.label is not None or r.predicate in eavc.STEP_PREDICATES
                for r in op.rows
            )
            assert has_body_row or has_steps, f"{os.path.basename(path)}:{op.name} has no body"


def test_stdlib_clock_minutes_to_seconds_pure_op():
    # WS3-107: a pure stdlib step-body op unit-tested directly.
    stdlib = open(os.path.join(STD, "standard.clock.sem"), encoding="utf-8").read()
    main = (
        "P is project\nP module m\nP target console\nP entry main\n"
        'm is module\nm path a.b\nm purpose "p"\nm invariant "i"\nm exports main\n'
        "ExitCode is alias\nExitCode for Int32\n"
        "main is operation\nmain out ExitCode\nmain async no\n"
        'main purpose "p"\nmain invariant "i"\n'
        "main let mins immutable Int64 3\nmain let okCode immutable ExitCode 0\n"
        "main do conv\nmain do show\nmain return okCode\n"
        "conv is call\nconv in main\nconv invokes minutesToSeconds\n"
        "conv arg minutes Int64 mins\nconv out secs Int64\n"
        "show is call\nshow in main\nshow invokes console.writeIntegerLine\n"
        "show arg value Int64 secs\n"
    )
    proc = subprocess.run(
        [sys.executable, os.path.join(HERE, "eavc.py"), "run", "-"],
        input=stdlib + "\n" + main, capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "180"  # 3 min -> 180 s


def test_captured_output_replay_multiline_transcript():
    # X-066: a multi-line transcript is captured in order, deterministic across
    # record runs, and replayed side-effect-free.
    src = (
        "P is project\nP module m\nP target console\nP entry main\nP mode capturedOutputReplay\n"
        'm is module\nm path a.b\nm purpose "p"\nm invariant "i"\nm exports main\n'
        "ExitCode is alias\nExitCode for Int32\n"
        "stdoutWriter is capability\nstdoutWriter grants write console.stdout\n"
        'stdoutWriter purpose "p"\n'
        "main is operation\nmain out ExitCode\nmain effect write console.stdout\n"
        'main uses stdoutWriter\nmain async no\nmain purpose "p"\nmain invariant "i"\n'
        'main let firstLine immutable String "alpha"\n'
        'main let secondLine immutable String "beta"\n'
        "main let okCode immutable ExitCode 0\n"
        "main do writeFirst\nmain do writeSecond\nmain return okCode\n"
        "writeFirst is call\nwriteFirst in main\nwriteFirst invokes console.writeLine\n"
        "writeFirst arg text String firstLine\n"
        "writeSecond is call\nwriteSecond in main\nwriteSecond invokes console.writeLine\n"
        "writeSecond arg text String secondLine\n"
    )
    result = eavc.captured_output_replay(src)
    assert result["transcript"] == ["alpha", "beta"]
    assert result["deterministic"] is True
    assert result["sideEffectFree"] is True


def test_validator_reject_paths():
    # X-065: rejecting fixtures for the heavily-branched validators.
    rejects = [
        # _validate_enum: duplicate variant
        "E is enum\nE variant openState\nE variant openState\n",
        # _validate_enum: repr on a payload-carrying variant
        "E is enum\nE variant openState Int64\nE repr openState 1\n",
        # _validate_enum: repr names an unknown variant
        "E is enum\nE variant openState\nE repr doneState 1\n",
        # _validate_enum: all-or-none repr (partial repr)
        "E is enum\nE variant openState\nE variant doneState\nE repr openState 0\n",
        # _validate_async: `start` in a synchronous operation
        ("main is operation\nmain out ExitCode\nmain async no\n"
         'main purpose "p"\nmain invariant "i"\nmain let okCode immutable ExitCode 0\n'
         "main start t\nmain join t\nmain return okCode\n"
         "t is task\nt in main\nt invokes x.run\nExitCode is alias\nExitCode for Int32\n"),
        # _validate_labels: duplicate label
        ("main is operation\nmain out ExitCode\nmain async no\n"
         'main purpose "p"\nmain invariant "i"\nmain let okCode immutable ExitCode 0\n'
         "main goto dup\nmain at dup return okCode\nmain at dup return okCode\n"
         "ExitCode is alias\nExitCode for Int32\n"),
    ]
    for src in rejects:
        with pytest.raises(eavc.EavError):
            eavc.parse(src)


def _async_guard_program(resolve, guard_rows):
    return (
        "P is project\nP module m\nP target console\nP entry main\n"
        'm is module\nm path a.b\nm purpose "p"\nm invariant "i"\nm exports main\n'
        "ExitCode is alias\nExitCode for Int32\n"
        "main is operation\nmain out ExitCode\nmain async yes\n"
        'main purpose "p"\nmain invariant "i"\n'
        "main let one immutable Int64 1\nmain let two immutable Int64 2\n"
        "main let okCode immutable ExitCode 0\n"
        f"main start sumTask\nmain {resolve} sumTask\n" + guard_rows +
        "main return okCode\n"
        "main at ready return okCode\nmain at other return okCode\n"
        "sumTask is task\nsumTask in main\nsumTask invokes math.addInt64\n"
        "sumTask arg left Int64 one\nsumTask arg right Int64 two\nsumTask out sumResult Int64\n"
    )


def test_async_branch_guard_codegen():
    # X-063: ifReady (always-taken), ifPending (fall-through), ifCanceled
    # (fall-through after cancel) all lower + JIT-run on the single-thread backend.
    ready = _async_guard_program(
        "poll", "main branch ifReady sumTask goto ready\nmain branch ifPending sumTask goto other\n")
    for src in (ready,
                _async_guard_program("cancel", "main branch ifCanceled sumTask goto other\n")):
        assert not any(d.severity == "error" for d in eavc.lint(eavc.parse(src)))
        proc = subprocess.run(
            [sys.executable, os.path.join(HERE, "eavc.py"), "run", "-"],
            input=src, capture_output=True, text=True,
        )
        assert proc.returncode == 0, proc.stderr
    # ifError on a call with no catch is rejected (SS1041)
    bad = (
        "P is project\nP module m\nP target console\nP entry main\n"
        'm is module\nm path a.b\nm purpose "p"\nm invariant "i"\nm exports main\n'
        "ExitCode is alias\nExitCode for Int32\n"
        "main is operation\nmain out ExitCode\nmain async no\n"
        'main purpose "p"\nmain invariant "i"\nmain let okCode immutable ExitCode 0\n'
        'main let okText immutable String "x"\n'
        "main do w\nmain branch ifError w goto failed\nmain return okCode\n"
        "main at failed return okCode\n"
        "w is call\nw in main\nw invokes console.writeLine\nw arg text String okText\n"
    )
    with pytest.raises(eavc.EavError) as exc:
        eavc.lower_to_llvm(eavc.parse(bad))
    assert getattr(exc.value, "code", None) == "SS1041"


def _compare_ir(target, atype, va, vb):
    src = (
        "P is project\nP module m\nP target console\nP entry main\n"
        'm is module\nm path a.b\nm purpose "p"\nm invariant "i"\nm exports main\n'
        "ExitCode is alias\nExitCode for Int32\n"
        "main is operation\nmain out ExitCode\nmain async no\n"
        'main purpose "p"\nmain invariant "i"\n'
        f"main let a immutable {atype} {va}\nmain let b immutable {atype} {vb}\n"
        "main let okCode immutable ExitCode 0\nmain do cmp\nmain return okCode\n"
        f"cmp is call\ncmp in main\ncmp invokes {target}\n"
        f"cmp arg left {atype} a\ncmp arg right {atype} b\ncmp out result Bool\n"
    )
    return str(eavc.lower_to_llvm(eavc.parse(src)))


def test_compare_codegen_depth():
    # X-064: _emit_compare branches — String (strcmp), Float64 ordered/unordered,
    # and the ordering-on-String reject (SS1345).
    assert "strcmp" in _compare_ir("compare.equalString", "String", '"x"', '"y"')
    assert "fcmp" in _compare_ir("compare.equalFloat64", "Float64", "1.0", "2.0")
    assert "fcmp" in _compare_ir("compare.notEqualFloat64", "Float64", "1.0", "2.0")
    assert "fcmp" in _compare_ir("compare.lessThanFloat64", "Float64", "1.0", "2.0")
    with pytest.raises(eavc.EavError) as exc:
        _compare_ir("compare.lessThanString", "String", '"x"', '"y"')
    assert getattr(exc.value, "code", None) == "SS1345"


def test_diagnostic_emission_guard():
    # X-062: every diagnostic code in the registry is actually emitted somewhere
    # (a literal "CODE" appears beyond its registry definition), not merely
    # defined. Catches drift where a new code is registered without being wired.
    src = open(eavc.__file__, encoding="utf-8").read()
    unemitted = [c for c in eavc.DIAGNOSTICS if src.count(f'"{c}"') <= 1]
    assert not unemitted, f"codes defined but never emitted: {unemitted}"
    # probe the newly-wired codes to confirm they flow through to EavError.code
    probes = {
        "SS0002": "bad_name is record\n",                       # invalid identifier
        "SS0003": "error is record\n",                          # reserved word name
        "SS1010": "look is operation\nlook out Result Int64\n",  # out Result arity
    }
    for code, src_text in probes.items():
        with pytest.raises(eavc.EavError) as exc:
            eavc.parse(src_text)
        assert getattr(exc.value, "code", None) == code, (code, exc.value)


def test_lexer_edge_cases():
    # X-067: tokenize_line escapes, banned escapes, comments-in-strings, errors.
    tl = eavc.tokenize_line
    # supported escapes preserved verbatim in the single string token
    assert tl(r'x "a\nb\tc\"d\\e"') == ["x", r'"a\nb\tc\"d\\e"']
    assert tl(r'x "\x41"') == ["x", r'"\x41"']
    # `#` inside a string is literal; outside it starts a comment
    assert tl('x "a#b"') == ["x", '"a#b"']
    assert tl("foo bar # trailing comment") == ["foo", "bar"]
    assert tl("# whole-line comment") == []
    # banned / deferred escapes and malformed strings raise
    for bad in (r'x "a\rb"', r'x "a\0b"', r'x "\u{41}"', r'x "\q"',
                r'x "\x4"', r'x "\xZZ"', 'x "unterminated', r'x "trailing\\'):
        with pytest.raises(eavc.EavError):
            tl(bad)


def test_function_normalizes_to_operation():
    # WS1-027 / README §11: `is function` normalizes to an operation at parse and
    # reuses operation checks; legacy bare `function NAME` is rejected.
    prog = eavc.parse(
        "addOne is function\naddOne in n Int64\naddOne out Int64\n"
        "addOne let r immutable Int64 0\naddOne return r\n"
    )
    assert prog.entities["addOne"].kind == "operation"
    # reuses operation return-arity checks (void op returning a value is rejected)
    with pytest.raises(eavc.EavError):
        eavc.parse("get is function\nget let x immutable Int64 1\nget return x\n")
    # legacy verb-led `function NAME` is not an EAV row
    with pytest.raises(eavc.EavError):
        eavc.parse("function addOne\naddOne out Int64\n")


def test_alias_newtype_no_silent_coercion():
    # README §10 / WS1-031: passing the base type where an alias newtype is
    # required is a hard type error (no silent coercion).
    src = (
        "Acc is alias\nAcc for Int64\n"
        "addOne is operation\naddOne in n Acc\naddOne out Int64\n"
        "addOne let r immutable Int64 0\naddOne return r\n"
        "main is operation\nmain out ExitCode\nmain let base immutable Int64 5\n"
        'main do callIt\nmain let okCode immutable ExitCode 0\nmain return okCode\n'
        "callIt is call\ncallIt in main\ncallIt invokes addOne\n"
        'callIt discards "demo"\ncallIt arg n Int64 base\n'
    )
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(src)
    assert getattr(exc.value, "code", None) == "SS3710"


def test_alias_newtype_matching_type_ok():
    # Passing the alias newtype itself is accepted.
    src = (
        "Acc is alias\nAcc for Int64\n"
        "addOne is operation\naddOne in n Acc\naddOne out Int64\n"
        "addOne let r immutable Int64 0\naddOne return r\n"
        "main is operation\nmain out ExitCode\nmain let base immutable Acc 5\n"
        'main do callIt\nmain let okCode immutable ExitCode 0\nmain return okCode\n'
        "callIt is call\ncallIt in main\ncallIt invokes addOne\n"
        'callIt discards "demo"\ncallIt arg n Acc base\n'
    )
    eavc.parse(src)  # no raise


def test_loop_keyword_rejected():
    # README §17 #14: loop/while/each/break/continue are not predicates.
    for kw in ("loop", "while", "each", "break", "continue"):
        with pytest.raises(eavc.EavError):
            eavc.parse(f"main is operation\nmain out ExitCode\nmain {kw} x\n")


def test_reducible_cfg_no_warning():
    # countdown's single-entry loop is reducible -> no irreducible warning.
    prog = eavc.parse(open(os.path.join(EXAMPLES, "countdown.sem"), encoding="utf-8").read())
    assert "SS1315" not in {d.code for d in eavc.lint(prog)}


def test_irreducible_cfg_warns():
    # README §17 #15: a multi-entry loop (entry branches into both A and B,
    # which jump to each other) is irreducible.
    src = (
        "main is operation\nmain out ExitCode\n"
        "main let okCode immutable ExitCode 0\nmain let flag immutable Bool true\n"
        "main branch if flag goto blockB\n"
        "main at blockA do noopA\nmain goto blockB\n"
        "main at blockB do noopB\nmain goto blockA\n"
        "main return okCode\n"
        "noopA is call\nnoopA in main\nnoopA invokes console.writeLine\nnoopA arg text String t\n"
        "noopB is call\nnoopB in main\nnoopB invokes console.writeLine\nnoopB arg text String t\n"
        'main let t immutable String "x"\n'
    )
    assert "SS1315" in {d.code for d in eavc.lint(eavc.parse(src))}


def test_loop_no_exit_path_warns():
    # X-100 / §13 §33.3: a back-edge loop with no exit path (no return, no
    # branch/goto leaving the loop) is a likely infinite loop. No-op-failing: a
    # checker that ignores progress would not flag it.
    src = (
        "spin is operation\nspin out ExitCode\nspin async no\n"
        'spin purpose "p"\nspin invariant "i"\n'
        "spin let okCode immutable ExitCode 0\n"
        'spin let t immutable String "x"\n'
        "spin at loopTop do tick\nspin goto loopTop\nspin return okCode\n"
        "tick is call\ntick in spin\ntick invokes console.writeLine\ntick arg text String t\n"
    )
    assert "SS0950" in {d.code for d in eavc.lint(eavc.parse(src))}


def test_loop_invariant_exit_guard_warns():
    # X-100: an exit branch exists, but its guard is bound once before the loop
    # and never recomputed in the body -> no progress toward the exit.
    src = (
        "stuck is operation\nstuck out ExitCode\nstuck async no\n"
        'stuck purpose "p"\nstuck invariant "i"\n'
        "stuck let okCode immutable ExitCode 0\n"
        'stuck let t immutable String "x"\nstuck let shouldStop immutable Bool false\n'
        "stuck at loopTop do tick\nstuck branch if shouldStop goto loopEnd\n"
        "stuck goto loopTop\nstuck at loopEnd return okCode\n"
        "tick is call\ntick in stuck\ntick invokes console.writeLine\ntick arg text String t\n"
    )
    assert "SS0950" in {d.code for d in eavc.lint(eavc.parse(src))}


def test_counting_loop_makes_progress_no_warning():
    # X-100: the canonical counting loop recomputes its exit guard each iteration
    # and mutates the index -> progresses, so it must NOT warn.
    src = (
        "main is operation\nmain out ExitCode\nmain async no\n"
        'main purpose "p"\nmain invariant "i"\n'
        "main let okCode immutable ExitCode 0\n"
        "main let finalIndex immutable Int64 10\nmain let indexStep immutable Int64 1\n"
        "main let currentIndex mutable Int64 0\n"
        "main at loopStart do doneCall\nmain branch if loopDone goto loopEnd\n"
        "main do nextIndexCall\nmain set currentIndex nextIndex\nmain goto loopStart\n"
        "main at loopEnd return okCode\n"
        "doneCall is call\ndoneCall in main\ndoneCall invokes math.greaterThanOrEqualInt64\n"
        "doneCall arg left Int64 currentIndex\ndoneCall arg right Int64 finalIndex\n"
        "doneCall out loopDone Bool\n"
        "nextIndexCall is call\nnextIndexCall in main\nnextIndexCall invokes math.addInt64\n"
        "nextIndexCall arg left Int64 currentIndex\nnextIndexCall arg right Int64 indexStep\n"
        "nextIndexCall out nextIndex Int64\n"
    )
    assert "SS0950" not in {d.code for d in eavc.lint(eavc.parse(src))}


def _time_arith_src(time_type):
    return (
        f"{time_type} is alias\n{time_type} for Int64\n"
        "diff is operation\ndiff out Int64\ndiff async no\n"
        'diff purpose "p"\ndiff invariant "i"\n'
        f"diff in startInstant {time_type}\ndiff in endInstant {time_type}\n"
        "diff do sub\ndiff return span\n"
        "sub is call\nsub in diff\nsub invokes math.subtractInt64\n"
        f"sub arg left {time_type} endInstant\nsub arg right {time_type} startInstant\n"
        "sub out span Int64\n"
    )


def test_walltime_arithmetic_rejected():
    # X-095 / §30.5.3: measuring elapsed time (subtracting WallTime) is a hard
    # error — wall-clock time has no arithmetic. No-op-failing: a checker that
    # ignores the operand type would accept it (WallTime resolves to Int64).
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(_time_arith_src("WallTime"))
    assert getattr(exc.value, "code", None) == "SS3095"


def test_monotonic_instant_duration_accepted():
    # X-095: subtracting two MonotonicInstants yields a duration — the sound,
    # accepted form. It must NOT raise.
    prog = eavc.parse(_time_arith_src("MonotonicInstant"))
    assert "diff" in prog.entities


def test_walltime_local_arithmetic_rejected():
    # X-095: naive calendar arithmetic on WallTime (adding) is also rejected.
    src = (
        "WallTime is alias\nWallTime for Int64\n"
        "addDay is operation\naddDay out WallTime\naddDay async no\n"
        'addDay purpose "p"\naddDay invariant "i"\n'
        "addDay in now WallTime\naddDay let dayMillis immutable Int64 86400000\n"
        "addDay do bump\naddDay return later\n"
        "bump is call\nbump in addDay\nbump invokes math.addInt64\n"
        "bump arg left WallTime now\nbump arg right Int64 dayMillis\nbump out later WallTime\n"
    )
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(src)
    assert getattr(exc.value, "code", None) == "SS3095"


def test_decimal_op_with_float_operand_rejected():
    # X-093 / §10.6: exact decimal/money math has no Float operand. No-op-failing:
    # decimal.* is an external target, so the normal arg-type check skips it — the
    # dedicated precision rule is what catches the Float.
    src = (
        "Decimal is alias\nDecimal for Int64\n"
        "addPrice is operation\naddPrice out Decimal\naddPrice async no\n"
        'addPrice purpose "p"\naddPrice invariant "i"\n'
        "addPrice in base Decimal\naddPrice let bump immutable Float64 1.5\n"
        "addPrice do combine\naddPrice return total\n"
        "combine is call\ncombine in addPrice\ncombine invokes decimal.add\n"
        "combine arg left Decimal base\ncombine arg right Float64 bump\ncombine out total Decimal\n"
    )
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(src)
    assert getattr(exc.value, "code", None) == "SS3093"


def test_money_operand_in_float_math_rejected():
    # X-093: an exact Money value routed through Float arithmetic is rejected.
    src = (
        "Money is alias\nMoney for Int64\n"
        "scale is operation\nscale out Money\nscale async no\n"
        'scale purpose "p"\nscale invariant "i"\n'
        "scale in amount Money\nscale let factor immutable Float64 1.1\n"
        "scale do mul\nscale return scaled\n"
        "mul is call\nmul in scale\nmul invokes math.multiplyFloat64\n"
        "mul arg left Money amount\nmul arg right Float64 factor\nmul out scaled Money\n"
    )
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(src)
    assert getattr(exc.value, "code", None) == "SS3093"


def test_decimal_math_with_decimal_operands_accepted():
    # X-093: exact math through Decimal operands is the accepted form.
    src = (
        "Decimal is alias\nDecimal for Int64\n"
        "addPrice is operation\naddPrice out Decimal\naddPrice async no\n"
        'addPrice purpose "p"\naddPrice invariant "i"\n'
        "addPrice in base Decimal\naddPrice in bump Decimal\n"
        "addPrice do combine\naddPrice return total\n"
        "combine is call\ncombine in addPrice\ncombine invokes decimal.add\n"
        "combine arg left Decimal base\ncombine arg right Decimal bump\ncombine out total Decimal\n"
    )
    prog = eavc.parse(src)
    assert "addPrice" in prog.entities
    assert "SS3093" not in {d.code for d in eavc.lint(prog)}


def test_float_equality_warns():
    # X-093: exact equality on Float operands is a NaN/epsilon footgun -> warn.
    src = (
        "near is operation\nnear out Bool\nnear async no\n"
        'near purpose "p"\nnear invariant "i"\n'
        "near in left Float64\nnear in right Float64\n"
        "near do cmp\nnear return same\n"
        "cmp is call\ncmp in near\ncmp invokes math.equalFloat64\n"
        "cmp arg left Float64 left\ncmp arg right Float64 right\ncmp out same Bool\n"
    )
    assert "SS3094" in {d.code for d in eavc.lint(eavc.parse(src))}


def test_view_escapes_lifetime_rejected():
    # WS1-111 / §32.1 #9: a `mayEscape no` borrowed view returned out of its op
    # would outlive the borrowed source -> SS1560.
    src = (
        "makeView is operation\nmakeView out Slice\nmakeView async no\n"
        'makeView purpose "p"\nmakeView invariant "i"\n'
        "makeView in source Buffer\nmakeView do sliceBuf\nmakeView return theSlice\n"
        "sliceBuf is call\nsliceBuf in makeView\nsliceBuf invokes buffer.slice\n"
        "sliceBuf arg source Buffer source\nsliceBuf out theSlice Slice\n"
        "sliceBuf borrows source\nsliceBuf lifetime source\nsliceBuf mayEscape no\n"
    )
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(src)
    assert getattr(exc.value, "code", None) == "SS1560"


def test_view_declaring_cleanup_rejected():
    # WS1-111: a view borrows and never cleans — declaring `owns` on it is SS1566.
    src = (
        "makeView is operation\nmakeView out ExitCode\nmakeView async no\n"
        'makeView purpose "p"\nmakeView invariant "i"\n'
        "makeView in source Buffer\nmakeView let okCode immutable ExitCode 0\n"
        "makeView do sliceBuf\nmakeView return okCode\n"
        "sliceBuf is call\nsliceBuf in makeView\nsliceBuf invokes buffer.slice\n"
        "sliceBuf arg source Buffer source\nsliceBuf out theSlice Slice\n"
        "sliceBuf borrows source\nsliceBuf owns theSlice\n"
    )
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(src)
    assert getattr(exc.value, "code", None) == "SS1566"


def test_view_used_within_lifetime_accepted():
    # WS1-111: a `mayEscape no` view consumed inside its op (not returned) is fine.
    src = (
        "useView is operation\nuseView out ExitCode\nuseView async no\n"
        'useView purpose "p"\nuseView invariant "i"\n'
        "useView in source Buffer\nuseView let okCode immutable ExitCode 0\n"
        "useView do sliceBuf\nuseView do consume\nuseView return okCode\n"
        "sliceBuf is call\nsliceBuf in useView\nsliceBuf invokes buffer.slice\n"
        "sliceBuf arg source Buffer source\nsliceBuf out theSlice Slice\n"
        "sliceBuf borrows source\nsliceBuf lifetime source\nsliceBuf mayEscape no\n"
        "consume is call\nconsume in useView\nconsume invokes buffer.length\n"
        "consume arg view Slice theSlice\nconsume out n Int64\n"
    )
    prog = eavc.parse(src)
    assert "useView" in prog.entities
    codes = {d.code for d in eavc.lint(prog)}
    assert "SS1560" not in codes and "SS1566" not in codes


def _move_src(transfer_row, reuse=True):
    reuse_rows = (
        "main do reuseH\n" if reuse else ""
    )
    reuse_call = (
        "reuseH is call\nreuseH in main\nreuseH invokes resource.use\n"
        "reuseH arg h OpaquePointer handle\n" if reuse else ""
    )
    return (
        "main is operation\nmain out ExitCode\nmain async no\n"
        'main purpose "p"\nmain invariant "i"\n'
        "main let okCode immutable ExitCode 0\n"
        "main do openH\nmain do consumeH\n" + reuse_rows + "main return okCode\n"
        "openH is call\nopenH in main\nopenH invokes resource.open\n"
        "openH out handle OpaquePointer\nopenH owns handle\n"
        "consumeH is call\nconsumeH in main\nconsumeH invokes resource.transfer\n"
        + transfer_row + reuse_call
    )


def test_use_after_move_rejected():
    # WS1-113 / §32.1 #9: an owned handle reused after a `consumes yes` call is a
    # use-after-move (SS1564). No-op-failing: without move tracking the reuse looks
    # like an ordinary borrow.
    src = _move_src("consumeH arg h OpaquePointer handle consumes yes\n")
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(src)
    assert getattr(exc.value, "code", None) == "SS1564"


def test_takesownership_use_after_move_rejected():
    # WS1-113: the call-level `takesOwnership <handle>` form also moves it.
    src = _move_src(
        "consumeH arg h OpaquePointer handle\nconsumeH takesOwnership handle\n")
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(src)
    assert getattr(exc.value, "code", None) == "SS1564"


def test_borrow_consumes_no_keeps_owner():
    # WS1-113: `consumes no` is a borrow — the caller keeps ownership and may
    # reuse the handle afterward.
    src = _move_src("consumeH arg h OpaquePointer handle consumes no\n")
    prog = eavc.parse(src)
    assert "main" in prog.entities  # no SS1564 raised


def test_rawexternal_value_at_sink_rejected():
    # X-070 / §16: a `rawExternal`-typed value reaching a `trustConstraint`
    # sink slot without a validation boundary is a hard error (SS3070).
    src = (
        "RawSql is alias\nRawSql for String\nRawSql typeTrust rawExternal\n"
        "runQuery is operation\nrunQuery in sql RawSql\nrunQuery out ExitCode\n"
        'runQuery async no\nrunQuery purpose "p"\nrunQuery invariant "i"\n'
        "runQuery trustConstraint arg sql\n"
        "runQuery let okCode immutable ExitCode 0\nrunQuery return okCode\n"
        "main is operation\nmain out ExitCode\nmain async no\n"
        'main purpose "p"\nmain invariant "i"\n'
        'main let rawInput immutable RawSql "DROP TABLE users"\n'
        "main let okCode immutable ExitCode 0\nmain do callQuery\nmain return okCode\n"
        "callQuery is call\ncallQuery in main\ncallQuery invokes runQuery\n"
        "callQuery arg sql RawSql rawInput\ncallQuery out queryStatus ExitCode\n"
    )
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(src)
    assert getattr(exc.value, "code", None) == "SS3070"


def test_validated_value_at_sink_accepted():
    # X-070: a `validated`-typed value (post trust-boundary) passes the sink.
    src = (
        "SafeSql is alias\nSafeSql for String\nSafeSql typeTrust validated\n"
        "runQuery is operation\nrunQuery in sql SafeSql\nrunQuery out ExitCode\n"
        'runQuery async no\nrunQuery purpose "p"\nrunQuery invariant "i"\n'
        "runQuery trustConstraint arg sql\n"
        "runQuery let okCode immutable ExitCode 0\nrunQuery return okCode\n"
        "main is operation\nmain out ExitCode\nmain async no\n"
        'main purpose "p"\nmain invariant "i"\n'
        'main let safeInput immutable SafeSql "SELECT 1"\n'
        "main let okCode immutable ExitCode 0\nmain do callQuery\nmain return okCode\n"
        "callQuery is call\ncallQuery in main\ncallQuery invokes runQuery\n"
        "callQuery arg sql SafeSql safeInput\ncallQuery out queryStatus ExitCode\n"
    )
    prog = eavc.parse(src)
    assert "main" in prog.entities  # no SS3070 raised


def test_typetrust_unknown_label_rejected():
    # X-070: a typeTrust with an unknown label is rejected.
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse("Token is alias\nToken for String\nToken typeTrust bogusLabel\n")
    assert getattr(exc.value, "code", None) == "SS3070"


_SQL_SINK = (
    "SqlText is alias\nSqlText for String\n"
    "sqlExec is intrinsic\nsqlExec target sql.exec\nsqlExec arg sql SqlText\n"
    "sqlExec out rows Int64\nsqlExec trustConstraint arg sql SqlText\n"
)


def _sink_call_src(arg_row, extra=""):
    return (
        _SQL_SINK +
        "main is operation\nmain out ExitCode\nmain async no\n"
        'main purpose "p"\nmain invariant "i"\n'
        "main let okCode immutable ExitCode 0\n" + extra +
        "main do runSql\nmain return okCode\n"
        "runSql is call\nrunSql in main\nrunSql invokes sql.exec\n"
        + arg_row + "runSql out rows Int64\n"
    )


def test_plain_string_into_typed_sink_rejected():
    # X-071 / §16: a plain String into a SqlText sink is rejected — build the
    # trusted type at a boundary, never pass raw/untyped interpreter input.
    src = _sink_call_src(
        "runSql arg sql String rawText\n",
        extra='main let rawText immutable String "SELECT 1"\n')
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(src)
    assert getattr(exc.value, "code", None) == "SS3071"


def test_trusted_type_into_sink_accepted():
    # X-071: the required trusted type (SqlText) is accepted at the sink.
    src = _sink_call_src(
        "runSql arg sql SqlText safeText\n",
        extra='main let safeText immutable SqlText "SELECT 1"\n')
    prog = eavc.parse(src)
    assert "main" in prog.entities  # no SS3071


def test_string_concat_into_sink_rejected():
    # X-071 / §30.2.2: a `string.concat` result may never reach an interpreter
    # sink (no string-built queries), even if its type token matches.
    src = _sink_call_src(
        "runSql arg sql SqlText builtText\n",
        extra=(
            'main let prefix immutable String "SELECT * FROM t WHERE id="\n'
            'main let suffix immutable String "1"\n'
            "main do buildSql\n"
            "buildSql is call\nbuildSql in main\nbuildSql invokes string.concat\n"
            "buildSql arg left String prefix\nbuildSql arg right String suffix\n"
            "buildSql out builtText SqlText\n"
        ))
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(src)
    assert getattr(exc.value, "code", None) == "SS3071"


def test_secret_to_console_rejected():
    # X-072 / §30.1.1: a secret value written to an observable sink is rejected.
    src = (
        "ApiKey is alias\nApiKey for String\nApiKey typeTrust secret\n"
        "leak is operation\nleak out ExitCode\nleak async no\n"
        'leak purpose "p"\nleak invariant "i"\n'
        "leak in key ApiKey\nleak let okCode immutable ExitCode 0\n"
        "leak do show\nleak return okCode\n"
        "show is call\nshow in leak\nshow invokes console.writeLine\n"
        "show arg text ApiKey key\n"
    )
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(src)
    assert getattr(exc.value, "code", None) == "SS3072"


def test_hardcoded_secret_literal_rejected():
    # X-072 / §8: a secret-typed binding initialized from a literal is rejected.
    src = (
        "ApiKey is alias\nApiKey for String\nApiKey typeTrust secret\n"
        'hardKey is storage module immutable ApiKey "sk-deadbeef"\n'
        "main is operation\nmain out ExitCode\nmain async no\n"
        'main purpose "p"\nmain invariant "i"\n'
        "main let okCode immutable ExitCode 0\nmain return okCode\n"
    )
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(src)
    assert getattr(exc.value, "code", None) == "SS3072"


def test_secret_consumed_by_verify_accepted():
    # X-072: a secret is usable — passing it to a non-observable verify op is fine.
    src = (
        "Secret is alias\nSecret for String\nSecret typeTrust secret\n"
        "checkAuth is operation\ncheckAuth out Bool\ncheckAuth async no\n"
        'checkAuth purpose "p"\ncheckAuth invariant "i"\n'
        "checkAuth in token Secret\ncheckAuth do verify\ncheckAuth return ok\n"
        "verify is call\nverify in checkAuth\nverify invokes bcrypt.verifyPassword\n"
        "verify arg password Secret token\nverify out ok Bool\n"
    )
    prog = eavc.parse(src)
    assert "checkAuth" in prog.entities  # no SS3072


def test_secret_variable_compare_rejected():
    # X-074 / §13: comparing a secret with `compare.*`/`math.*` equality leaks via
    # timing -> SS3074. No-op-failing: an ordinary compare would be accepted.
    src = (
        "Secret is alias\nSecret for String\nSecret typeTrust secret\n"
        "checkTok is operation\ncheckTok out Bool\ncheckTok async no\n"
        'checkTok purpose "p"\ncheckTok invariant "i"\n'
        "checkTok in given Secret\ncheckTok in expected Secret\n"
        "checkTok do cmp\ncheckTok return same\n"
        "cmp is call\ncmp in checkTok\ncmp invokes compare.equalString\n"
        "cmp arg left Secret given\ncmp arg right Secret expected\ncmp out same Bool\n"
    )
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(src)
    assert getattr(exc.value, "code", None) == "SS3074"


def test_secret_constant_time_compare_accepted():
    # X-074: `crypto.equalConstantTime` is the sanctioned secret comparison.
    src = (
        "Secret is alias\nSecret for String\nSecret typeTrust secret\n"
        "checkTok is operation\ncheckTok out Bool\ncheckTok async no\n"
        'checkTok purpose "p"\ncheckTok invariant "i"\n'
        "checkTok in given Secret\ncheckTok in expected Secret\n"
        "checkTok do cmp\ncheckTok return same\n"
        "cmp is call\ncmp in checkTok\ncmp invokes crypto.equalConstantTime\n"
        "cmp arg left Secret given\ncmp arg right Secret expected\ncmp out same Bool\n"
    )
    prog = eavc.parse(src)
    assert "checkTok" in prog.entities  # no SS3074


def test_suppress_deny_tier_rejected():
    # WS2-072: a deny-tier (T0/T1/T2) code is non-suppressible — `suppress` of one
    # is itself an error (SS5402), and the underlying diagnostic stays in effect.
    src = (
        "main is operation\nmain out ExitCode\nmain async no\n"
        'main purpose "p"\nmain invariant "i"\n'
        'main suppress SS3070 because "we accept the risk"\n'
        "main let okCode immutable ExitCode 0\nmain return okCode\n"
    )
    assert "SS5402" in {d.code for d in eavc.lint(eavc.parse(src))}


def test_suppress_advisory_tier_allowed():
    # WS2-072: an advisory (T3) code may be suppressed with a `because`; the
    # suppressed diagnostic is dropped and no SS5402 is raised.
    base = (
        "near is operation\nnear out Bool\nnear async no\n"
        'near purpose "p"\nnear invariant "i"\n'
        "near in left Float64\nnear in right Float64\n"
        "near do cmp\nnear return same\n"
        "cmp is call\ncmp in near\ncmp invokes math.equalFloat64\n"
        "cmp arg left Float64 left\ncmp arg right Float64 right\ncmp out same Bool\n"
    )
    assert "SS3094" in {d.code for d in eavc.lint(eavc.parse(base))}  # fires by default
    suppressed = base + 'cmp suppress SS3094 because "tolerance not needed here"\n'
    codes = {d.code for d in eavc.lint(eavc.parse(suppressed))}
    assert "SS3094" not in codes and "SS5402" not in codes


def test_every_diagnostic_code_is_tier_classified():
    # WS2-072: every registry code carries a tier in T0..T4 (deny vs advisory).
    for code, meta in eavc.DIAGNOSTICS.items():
        assert meta.get("tier") in ("T0", "T1", "T2", "T3", "T4"), code


def _decode_src(limit_row=""):
    return (
        "RawJson is alias\nRawJson for String\nRawJson typeTrust rawExternal\n"
        "JsonDoc is alias\nJsonDoc for OpaquePointer\n"
        "parseReq is operation\nparseReq out ExitCode\nparseReq async no\n"
        'parseReq purpose "p"\nparseReq invariant "i"\n'
        "parseReq in body RawJson\nparseReq let okCode immutable ExitCode 0\n"
        "parseReq do decode\nparseReq return okCode\n"
        "decode is call\ndecode in parseReq\ndecode invokes json.parse\n"
        "decode arg text RawJson body\n" + limit_row +
        "decode out value JsonDoc\ndecode catch e JsonError\n"
        "JsonError is error\n"
    )


def test_untrusted_decode_without_limit_rejected():
    # X-077 / §16: decoding a rawExternal input with no `limit maximumBytes` is a
    # deserialization-DoS hole -> SS3077.
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(_decode_src())
    assert getattr(exc.value, "code", None) == "SS3077"


def test_untrusted_decode_with_limit_accepted():
    # X-077: the same decode with a `limit maximumBytes` cap is accepted.
    prog = eavc.parse(_decode_src("decode limit maximumBytes 65536\n"))
    assert "parseReq" in prog.entities


def _token_gen_src(rng_target):
    return (
        "mintToken is operation\nmintToken out ExitCode\nmintToken async no\n"
        'mintToken purpose "p"\nmintToken invariant "i"\n'
        "mintToken let okCode immutable ExitCode 0\nmintToken let seedSize immutable Int64 32\n"
        "mintToken do draw\nmintToken do gen\nmintToken return okCode\n"
        "draw is call\ndraw in mintToken\ndraw invokes " + rng_target + "\n"
        "draw arg size Int64 seedSize\ndraw out seedValue Int64\n"
        "gen is call\ngen in mintToken\ngen invokes crypto.generateToken\n"
        "gen arg source Int64 seedValue\ngen out token String\n"
    )


def test_seeded_rng_into_security_gen_rejected():
    # X-073 / §30.5.3: a deterministic-RNG draw feeding a token generator is a
    # hard error — security material needs the CSPRNG.
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(_token_gen_src("random.deterministic"))
    assert getattr(exc.value, "code", None) == "SS3073"


def test_entropy_rng_into_security_gen_accepted():
    # X-073: drawing from the CSPRNG (random.entropy) is the accepted path.
    prog = eavc.parse(_token_gen_src("random.entropy"))
    assert "mintToken" in prog.entities


def test_nonce_reuse_rejected():
    # X-073: a nonce is affine — consuming it in two cryptographic calls is a
    # nonce-reuse error (SS3073).
    src = (
        "seal is operation\nseal out ExitCode\nseal async no\n"
        'seal purpose "p"\nseal invariant "i"\n'
        "seal let okCode immutable ExitCode 0\nseal in plainA String\nseal in plainB String\n"
        "seal do makeNonce\nseal do encA\nseal do encB\nseal return okCode\n"
        "makeNonce is call\nmakeNonce in seal\nmakeNonce invokes crypto.generateNonce\n"
        "makeNonce out nonce OpaquePointer\n"
        "encA is call\nencA in seal\nencA invokes crypto.encrypt\n"
        "encA arg nonce OpaquePointer nonce\nencA arg plaintext String plainA\nencA out ctA String\n"
        "encB is call\nencB in seal\nencB invokes crypto.encrypt\n"
        "encB arg nonce OpaquePointer nonce\nencB arg plaintext String plainB\nencB out ctB String\n"
    )
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(src)
    assert getattr(exc.value, "code", None) == "SS3073"


def test_nonce_single_use_accepted():
    # X-073: a nonce consumed by exactly one cryptographic call is fine.
    src = (
        "seal is operation\nseal out ExitCode\nseal async no\n"
        'seal purpose "p"\nseal invariant "i"\n'
        "seal let okCode immutable ExitCode 0\nseal in plain String\n"
        "seal do makeNonce\nseal do enc\nseal return okCode\n"
        "makeNonce is call\nmakeNonce in seal\nmakeNonce invokes crypto.generateNonce\n"
        "makeNonce out nonce OpaquePointer\n"
        "enc is call\nenc in seal\nenc invokes crypto.encrypt\n"
        "enc arg nonce OpaquePointer nonce\nenc arg plaintext String plain\nenc out ct String\n"
    )
    prog = eavc.parse(src)
    assert "seal" in prog.entities


def test_path_traversal_literal_rejected():
    # X-076 / §8: a `..` path literal at a filesystem op escapes its root -> SS3076.
    src = (
        "readIt is operation\nreadIt out ExitCode\nreadIt async no\n"
        'readIt purpose "p"\nreadIt invariant "i"\n'
        'readIt let badPath immutable String "../../etc/passwd"\n'
        "readIt let okCode immutable ExitCode 0\nreadIt do rf\nreadIt return okCode\n"
        "rf is call\nrf in readIt\nrf invokes fs.readFile\n"
        "rf arg path String badPath\nrf out contents String\nrf catch e FsError\n"
        "FsError is error\n"
    )
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(src)
    assert getattr(exc.value, "code", None) == "SS3076"


def test_absolute_path_literal_rejected():
    # X-076: an absolute path literal also escapes a confined root.
    src = (
        "readIt is operation\nreadIt out ExitCode\nreadIt async no\n"
        'readIt purpose "p"\nreadIt invariant "i"\n'
        'readIt let absPath immutable String "/etc/shadow"\n'
        "readIt let okCode immutable ExitCode 0\nreadIt do rf\nreadIt return okCode\n"
        "rf is call\nrf in readIt\nrf invokes fs.readFile\n"
        "rf arg path String absPath\nrf out contents String\nrf catch e FsError\n"
        "FsError is error\n"
    )
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(src)
    assert getattr(exc.value, "code", None) == "SS3076"


def test_confined_relative_path_accepted():
    # X-076: a plain relative filename under the root is fine.
    src = (
        "readIt is operation\nreadIt out ExitCode\nreadIt async no\n"
        'readIt purpose "p"\nreadIt invariant "i"\n'
        'readIt let okPath immutable String "data/report.txt"\n'
        "readIt let okCode immutable ExitCode 0\nreadIt do rf\nreadIt return okCode\n"
        "rf is call\nrf in readIt\nrf invokes fs.readFile\n"
        "rf arg path String okPath\nrf out contents String\nrf catch e FsError\n"
        "FsError is error\n"
    )
    prog = eavc.parse(src)
    assert "readIt" in prog.entities


def _fetch_src(url):
    return (
        "fetchIt is operation\nfetchIt out ExitCode\nfetchIt async no\n"
        'fetchIt purpose "p"\nfetchIt invariant "i"\n'
        f'fetchIt let endpoint immutable String "{url}"\n'
        "fetchIt let okCode immutable ExitCode 0\nfetchIt do fetch\nfetchIt return okCode\n"
        "fetch is call\nfetch in fetchIt\nfetch invokes net.fetchText\n"
        "fetch arg url String endpoint\nfetch out body String\nfetch catch e NetError\n"
        "NetError is error\n"
    )


def test_ssrf_internal_address_rejected():
    # X-075 / §8: an outbound request to a loopback/metadata address is SSRF.
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(_fetch_src("http://169.254.169.254/latest/meta-data/"))
    assert getattr(exc.value, "code", None) == "SS3075"


def test_ssrf_localhost_rejected():
    # X-075: localhost is internal.
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(_fetch_src("http://localhost:8080/admin"))
    assert getattr(exc.value, "code", None) == "SS3075"


def test_ssrf_external_host_accepted():
    # X-075: an external host is fine (the runtime allowlist refines this further).
    prog = eavc.parse(_fetch_src("https://api.example.com/v1/users"))
    assert "fetchIt" in prog.entities


def _untrusted_fetch_src(bound_row=""):
    return (
        "RawUrl is alias\nRawUrl for String\nRawUrl typeTrust rawExternal\n"
        "proxy is operation\nproxy out ExitCode\nproxy async no\n"
        'proxy purpose "p"\nproxy invariant "i"\n'
        "proxy in userUrl RawUrl\nproxy let okCode immutable ExitCode 0\n"
        "proxy do fetch\nproxy return okCode\n"
        "fetch is call\nfetch in proxy\nfetch invokes net.fetchText\n"
        "fetch arg url RawUrl userUrl\n" + bound_row +
        "fetch out body String\nfetch catch e NetError\nNetError is error\n"
    )


def test_unbounded_untrusted_external_call_rejected():
    # X-078 / §27: external I/O over untrusted input without a timeout/budget is a
    # DoS hole -> SS3078.
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(_untrusted_fetch_src())
    assert getattr(exc.value, "code", None) == "SS3078"


def test_bounded_untrusted_external_call_accepted():
    # X-078: a `timeout` row bounds the call.
    prog = eavc.parse(_untrusted_fetch_src("fetch timeout 5000ms\n"))
    assert "proxy" in prog.entities


def _disclosure_src(boundary_row=""):
    return (
        "DbError is error\nDbError typeTrust trustedInternal\n"
        "sendToClient is intrinsic\nsendToClient target http.writeResponse\n"
        "sendToClient arg body DbError\nsendToClient clientResponse arg body\n"
        "sendToClient out written Int32\n"
        "handler is operation\nhandler out ExitCode\nhandler async no\n"
        'handler purpose "p"\nhandler invariant "i"\n'
        "handler in failure DbError\n" + boundary_row +
        "handler let okCode immutable ExitCode 0\nhandler do leak\nhandler return okCode\n"
        "leak is call\nleak in handler\nleak invokes http.writeResponse\n"
        "leak arg body DbError failure\nleak out w Int32\n"
    )


def test_internal_error_to_client_rejected():
    # X-079 / §16/§25: a trustedInternal error reaching a clientResponse sink with
    # no errorBoundary mapping is an information-disclosure error (SS3079).
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(_disclosure_src())
    assert getattr(exc.value, "code", None) == "SS3079"


def test_internal_error_with_boundary_accepted():
    # X-079: an `errorBoundary` mapping to a client-safe error clears it.
    src = _disclosure_src("handler errorBoundary DbError ClientError\n")
    prog = eavc.parse(src)
    assert "handler" in prog.entities


def _utf8_decode_src(out_type):
    return (
        "RawBytes is alias\nRawBytes for OpaquePointer\nRawBytes typeTrust rawExternal\n"
        + ("ValidText is alias\nValidText for String\nValidText typeTrust validated\n"
           if out_type == "ValidText" else "") +
        "ingest is operation\ningest out ExitCode\ningest async no\n"
        'ingest purpose "p"\ningest invariant "i"\n'
        "ingest in raw RawBytes\ningest let okCode immutable ExitCode 0\n"
        "ingest do decode\ningest return okCode\n"
        "decode is call\ndecode in ingest\ndecode invokes bytes.toText\n"
        f"decode arg bytes RawBytes raw\ndecode out text {out_type}\n"
    )


def test_unvalidated_bytes_to_text_rejected():
    # X-096 / §10.6: decoding untrusted bytes into a plain String (no validation
    # boundary) is rejected.
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(_utf8_decode_src("String"))
    assert getattr(exc.value, "code", None) == "SS3096"


def test_validated_bytes_to_text_accepted():
    # X-096: decoding into a `validated` text type (a UTF-8 boundary) is accepted.
    prog = eavc.parse(_utf8_decode_src("ValidText"))
    assert "ingest" in prog.entities


def test_protection_optout_without_because_rejected():
    # X-080 / §14: a security opt-out must carry a `because` rationale -> SS3080.
    src = (
        "main is operation\nmain out ExitCode\nmain async no\n"
        'main purpose "p"\nmain invariant "i"\n'
        "main optOut autoEscape\n"
        "main let okCode immutable ExitCode 0\nmain return okCode\n"
    )
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(src)
    assert getattr(exc.value, "code", None) == "SS3080"


def test_protection_optout_with_because_accepted():
    # X-080: a justified opt-out is explicit + greppable, and accepted.
    src = (
        "main is operation\nmain out ExitCode\nmain async no\n"
        'main purpose "p"\nmain invariant "i"\n'
        'main optOut autoEscape because "rendering a pre-sanitized trusted fragment"\n'
        "main let okCode immutable ExitCode 0\nmain return okCode\n"
    )
    prog = eavc.parse(src)
    assert "main" in prog.entities


def test_security_coverage_matrix_consistent():
    # X-083 / §29 #19: every matrix row is classified, every named defense code is a
    # real registry diagnostic, and out-of-language rows carry a note (no orphans).
    valid_status = {"covered", "partial", "out-of-language"}
    for r in eavc.SECURITY_COVERAGE:
        assert r["status"] in valid_status, r
        assert r["vuln"] and r["asset"] and r["note"], r
        if r["code"] is not None:
            assert r["code"] in eavc.DIAGNOSTICS, r["code"]
        if r["status"] == "out-of-language":
            assert r["todo"] is None and r["code"] is None, r
        else:
            assert r["todo"] is not None, r  # an in-language defense has an owning todo


def test_security_coverage_matrix_covers_implemented_codes():
    # X-083: every security/safety diagnostic the workstream landed is represented
    # in the matrix (the matrix tracks the real enforced defenses, no gaps).
    matrix_codes = {r["code"] for r in eavc.SECURITY_COVERAGE if r["code"]}
    for code in ("SS3070", "SS3071", "SS3072", "SS3073", "SS3074", "SS3075",
                 "SS3076", "SS3077", "SS3078", "SS3079", "SS3080", "SS3096",
                 "SS2805", "SS1564"):
        assert code in matrix_codes, code


def test_security_matrix_markdown_renders():
    # X-083: the living matrix renders as a Markdown table from the data.
    md = eavc.security_matrix_markdown()
    assert "threat-model coverage matrix" in md
    assert md.count("\n|") >= len(eavc.SECURITY_COVERAGE)  # a row per entry


def test_defect_ledger_covers_all_families():
    # X-101 / §29 #19: the ledger extends the security matrix to memory +
    # correctness/reliability families; every row is classified, named codes are
    # real, and out-of-language rows carry a note. Every defect family is present.
    valid = {"covered", "partial", "out-of-language"}
    assets = set()
    for r in eavc.DEFECT_LEDGER:
        assert r["status"] in valid and r["vuln"] and r["asset"] and r["note"], r
        if r["code"] is not None:
            assert r["code"] in eavc.DIAGNOSTICS, r["code"]
        if r["status"] == "out-of-language":
            assert r["code"] is None, r
        else:
            assert r["todo"] is not None, r
        assets.add(r["asset"])
    # all major defect families are represented
    assert {"memory", "correctness", "reliability", "trust"} <= assets
    # the ledger is a superset of the security matrix
    assert len(eavc.DEFECT_LEDGER) > len(eavc.SECURITY_COVERAGE)


def test_defect_ledger_markdown_renders():
    md = eavc.defect_ledger_markdown()
    assert "defect-class coverage ledger" in md
    assert md.count("\n|") >= len(eavc.DEFECT_LEDGER)


def test_operand_width_drift_rejected():
    # WS2-085 / §10.6: mixing integer operand widths in a math op is rejected.
    src = (
        "calc is operation\ncalc out Int64\ncalc async no\n"
        'calc purpose "p"\ncalc invariant "i"\n'
        "calc let small immutable Int32 1\ncalc let big immutable Int64 2\n"
        "calc do add\ncalc return sum\n"
        "add is call\nadd in calc\nadd invokes math.addInt64\n"
        "add arg left Int32 small\nadd arg right Int64 big\nadd out sum Int64\n"
    )
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(src)
    assert getattr(exc.value, "code", None) == "SS3110"


def test_constant_division_by_zero_rejected():
    # WS2-085 / §33.5: division by a constant 0 is undefined -> SS3111.
    src = (
        "calc is operation\ncalc out Int64\ncalc async no\n"
        'calc purpose "p"\ncalc invariant "i"\n'
        "calc let n immutable Int64 10\ncalc let zero immutable Int64 0\n"
        "calc do div\ncalc return q\n"
        "div is call\ndiv in calc\ndiv invokes math.divideInt64\n"
        "div arg left Int64 n\ndiv arg right Int64 zero\ndiv out q Int64\n"
    )
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(src)
    assert getattr(exc.value, "code", None) == "SS3111"


def test_constant_overwide_shift_rejected():
    # WS2-085 / §33.5: a shift by a constant >= operand width is undefined.
    src = (
        "calc is operation\ncalc out Int64\ncalc async no\n"
        'calc purpose "p"\ncalc invariant "i"\n'
        "calc let n immutable Int64 1\ncalc let amt immutable Int64 99\n"
        "calc do sh\ncalc return r\n"
        "sh is call\nsh in calc\nsh invokes math.shiftLeftInt64\n"
        "sh arg left Int64 n\nsh arg right Int64 amt\nsh out r Int64\n"
    )
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(src)
    assert getattr(exc.value, "code", None) == "SS3111"


def test_same_width_nonzero_division_accepted():
    # WS2-085: matching widths + a non-zero divisor are fine.
    src = (
        "calc is operation\ncalc out Int64\ncalc async no\n"
        'calc purpose "p"\ncalc invariant "i"\n'
        "calc let n immutable Int64 10\ncalc let d immutable Int64 2\n"
        "calc do div\ncalc return q\n"
        "div is call\ndiv in calc\ndiv invokes math.divideInt64\n"
        "div arg left Int64 n\ndiv arg right Int64 d\ndiv out q Int64\n"
    )
    prog = eavc.parse(src)
    assert "calc" in prog.entities


def _shared_state_src(guard_decl="hitCount guard hitCountLock\n",
                      set_row="main setShared hitCount seven protectedBy hitCountLock\n",
                      read_row="main readShared currentHits Int64 hitCount protectedBy hitCountLock\n",
                      scope="module"):
    return (
        "Counter is project\nCounter module appCounter\n"
        "Counter target console\nCounter entry main\n"
        "appCounter is module\nappCounter path a.b\n"
        'appCounter purpose "p"\nappCounter invariant "i"\n'
        "ExitCode is alias\nExitCode for Int32\n"
        "hitCount is sharedState\n" + f"hitCount scope {scope}\n" +
        "hitCount type Int64\nhitCount mutability mutable\nhitCount value 0\n"
        + guard_decl +
        "main is operation\nmain out ExitCode\nmain async no\n"
        'main purpose "p"\nmain invariant "i"\n'
        "main let okCode immutable ExitCode 0\nmain let seven immutable Int64 7\n"
        + set_row + read_row + "main do show\nmain return okCode\n"
        "show is call\nshow in main\nshow invokes console.writeIntegerLine\n"
        "show arg value Int64 currentHits\n"
    )


def test_shared_state_guarded_access_jit_runs():
    # WS2-083: a sharedState read/write held under its guard token JIT-runs (the
    # global is set to 7 and read back). No-op-failing: a checker that ignored the
    # construct could not lower readShared/setShared to a real load/store.
    src = _shared_state_src()
    assert not any(d.severity == "error" for d in eavc.lint(eavc.parse(src)))
    proc = subprocess.run(
        [sys.executable, os.path.join(HERE, "eavc.py"), "run", "-"],
        input=src, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "7"


def test_shared_state_unguarded_access_rejected():
    # WS2-083: accessing shared state without holding its guard token -> SS3083.
    src = _shared_state_src(set_row="main setShared hitCount seven\n")
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(src)
    assert getattr(exc.value, "code", None) == "SS3083"


def test_shared_state_wrong_guard_rejected():
    # WS2-083: holding the wrong token is still unguarded -> SS3083.
    src = _shared_state_src(
        set_row="main setShared hitCount seven protectedBy someOtherLock\n")
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(src)
    assert getattr(exc.value, "code", None) == "SS3083"


def test_shared_state_bad_scope_rejected():
    # WS2-083: a sharedState scope must be process or module -> SS3084.
    src = _shared_state_src(scope="thread")
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(src)
    assert getattr(exc.value, "code", None) == "SS3084"


_ARENA_SRC = (
    "Arena is project\nArena module appArena\n"
    "Arena target console\nArena entry main\n"
    "appArena is module\nappArena path a.b\n"
    'appArena purpose "p"\nappArena invariant "i"\n'
    "ExitCode is alias\nExitCode for Int32\n"
    "requestArena is region\nrequestArena strategy arena\nrequestArena scope main\n"
    "arenaAllocCap is capability\narenaAllocCap grants allocate heap.requestArena\n"
    "main is operation\nmain out ExitCode\nmain async no\n"
    'main purpose "p"\nmain invariant "i"\n'
    "main uses arenaAllocCap\nmain effect allocate heap.requestArena\n"
    "main let okCode immutable ExitCode 0\n"
    "main allocateIn requestArena bufferA OpaquePointer\n"
    "main allocateIn requestArena bufferB OpaquePointer\n"
    "main releaseRegion requestArena\nmain return okCode\n"
)


def test_region_arena_allocates_and_frees_jit_runs():
    # WS1-112: an arena allocates N slabs and frees them at scope exit. No-op-
    # failing: the IR must emit real malloc/free calls (an ignored construct would
    # emit neither), and it JIT-runs.
    assert not any(d.severity == "error" for d in eavc.lint(eavc.parse(_ARENA_SRC)))
    ir = str(eavc.lower_to_llvm(eavc.parse(_ARENA_SRC)))
    assert '@"malloc"' in ir and '@"free"' in ir
    assert ir.count('call void @"free"') >= 2  # one free per allocated slab
    proc = subprocess.run(
        [sys.executable, os.path.join(HERE, "eavc.py"), "run", "-"],
        input=_ARENA_SRC, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr


def test_region_allocate_without_capability_rejected():
    # WS1-112 / §8: allocating in a region with no allocator capability -> SS1563.
    src = _ARENA_SRC.replace("main uses arenaAllocCap\n", "")
    src = src.replace("main effect allocate heap.requestArena\n", "")
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(src)
    assert getattr(exc.value, "code", None) == "SS1563"


def test_region_free_mismatch_rejected():
    # WS1-112: releasing a region the op never allocated into -> SS1562.
    src = _ARENA_SRC.replace(
        "requestArena is region\nrequestArena strategy arena\nrequestArena scope main\n",
        "requestArena is region\nrequestArena strategy arena\nrequestArena scope main\n"
        "otherArena is region\notherArena strategy arena\notherArena scope main\n",
    ).replace("main releaseRegion requestArena\n", "main releaseRegion otherArena\n")
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(src)
    assert getattr(exc.value, "code", None) == "SS1562"


def test_buffer_get_without_error_path_rejected():
    # WS1-115 / §10.6: a bounds-checked buffer read with no `catch` drops the
    # out-of-bounds error -> SS1568.
    src = (
        "Buffer is alias\nBuffer for OpaquePointer\n"
        "readByte is operation\nreadByte out ExitCode\nreadByte async no\n"
        'readByte purpose "p"\nreadByte invariant "i"\n'
        "readByte in buf Buffer\nreadByte let idx immutable Int64 0\n"
        "readByte let okCode immutable ExitCode 0\nreadByte do get\nreadByte return okCode\n"
        "get is call\nget in readByte\nget invokes buffer.get\n"
        "get arg buffer Buffer buf\nget arg index Int64 idx\nget out value Byte\n"
    )
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(src)
    assert getattr(exc.value, "code", None) == "SS1568"


def test_buffer_get_with_error_path_accepted():
    # WS1-115: binding `catch BufferBoundsError` handles the bounds failure.
    src = (
        "Buffer is alias\nBuffer for OpaquePointer\n"
        "BufferBoundsError is error\n"
        "readByte is operation\nreadByte out ExitCode\nreadByte async no\n"
        'readByte purpose "p"\nreadByte invariant "i"\n'
        "readByte in buf Buffer\nreadByte let idx immutable Int64 0\n"
        "readByte let okCode immutable ExitCode 0\nreadByte do get\n"
        "readByte branch ifError get goto oob\nreadByte return okCode\n"
        "readByte at oob return okCode\n"
        "get is call\nget in readByte\nget invokes buffer.get\n"
        "get arg buffer Buffer buf\nget arg index Int64 idx\nget out value Byte\n"
        "get catch boundsErr BufferBoundsError\n"
    )
    prog = eavc.parse(src)
    assert "readByte" in prog.entities


def test_buffer_slice_view_cannot_escape():
    # WS1-115 + WS1-111: a buffer.slice returns a Slice that borrows the buffer
    # (mayEscape no); returning it past the buffer's lifetime is rejected (SS1560).
    src = (
        "Buffer is alias\nBuffer for OpaquePointer\nSlice is alias\nSlice for OpaquePointer\n"
        "BufferBoundsError is error\n"
        "window is operation\nwindow out Slice\nwindow async no\n"
        'window purpose "p"\nwindow invariant "i"\n'
        "window in buf Buffer\nwindow let beginAt immutable Int64 0\nwindow let spanLen immutable Int64 4\n"
        "window do sliceIt\nwindow branch ifError sliceIt goto bad\nwindow return theSlice\n"
        "window at bad return theSlice\n"
        "sliceIt is call\nsliceIt in window\nsliceIt invokes buffer.slice\n"
        "sliceIt arg buffer Buffer buf\nsliceIt arg start Int64 beginAt\nsliceIt arg length Int64 spanLen\n"
        "sliceIt out theSlice Slice\nsliceIt catch e BufferBoundsError\n"
        "sliceIt borrows buf\nsliceIt lifetime buf\nsliceIt mayEscape no\n"
    )
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(src)
    assert getattr(exc.value, "code", None) == "SS1560"


def test_memory_concurrency_vocab_fully_absorbed():
    # WS1-117: the §1J memory + concurrency vocabulary is absorbed into the
    # language — the new entity kinds are registered, every new token is reserved,
    # and the token-sync drift guard is green (every token has a §5/§22 home).
    for kind in ("region", "sharedState"):
        assert kind in eavc.ENTITY_KINDS, kind
        assert kind in eavc.ALLOWED_PREDICATES, kind
    for tok in ("borrows", "lifetime", "mayEscape", "consumes", "takesOwnership",
                "region", "strategy", "capacity", "allocateIn", "releaseRegion",
                "sharedState", "guard", "protectedBy", "readShared", "setShared"):
        assert tok in eavc.RESERVED_WORDS, tok
    for step in ("readShared", "setShared", "allocateIn", "releaseRegion"):
        assert step in eavc.STEP_PREDICATES, step
    assert eavc.token_sync_drift() == set()  # all homed in §5/§22, no orphans


def test_ffi_allocator_missing_wrap_rejected():
    # WS1-116 / §26: an `unsafe yes` foreign allocator without wrapsAs/cleanedBy/
    # allocator is rejected (SS1569) — the raw pointer must re-enter as owned.
    src = (
        "rawMalloc is intrinsic\nrawMalloc target c.malloc\n"
        "rawMalloc arg size Int64\nrawMalloc out ptr OpaquePointer\n"
        "rawMalloc unsafe yes\nrawMalloc allocator c.heap\n"  # missing wrapsAs + cleanedBy
    )
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(src)
    assert getattr(exc.value, "code", None) == "SS1569"


def test_ffi_allocator_fully_wrapped_accepted():
    # WS1-116: a fully-wrapped foreign allocator (wrapsAs+cleanedBy+allocator) is
    # accepted — its result re-enters as an owned resource type.
    src = (
        "OwnedBuffer is alias\nOwnedBuffer for OpaquePointer\n"
        "allocBuffer is intrinsic\nallocBuffer target c.malloc\n"
        "allocBuffer arg size Int64\nallocBuffer out handle OwnedBuffer\n"
        "allocBuffer unsafe yes\nallocBuffer wrapsAs OwnedBuffer\n"
        "allocBuffer cleanedBy c.free\nallocBuffer allocator c.heap\n"
    )
    prog = eavc.parse(src)
    assert "allocBuffer" in prog.entities


def test_region_use_after_release_rejected():
    # WS1-120 SS1561: using a region-allocated value after releaseRegion.
    src = (
        "Reg is project\nReg module appReg\nReg target console\nReg entry main\n"
        "appReg is module\nappReg path a.b\n"
        'appReg purpose "p"\nappReg invariant "i"\nExitCode is alias\nExitCode for Int32\n'
        "rgn is region\nrgn strategy arena\nrgn scope main\n"
        "ac is capability\nac grants allocate heap.rgn\n"
        "main is operation\nmain out ExitCode\nmain async no\n"
        'main purpose "p"\nmain invariant "i"\nmain uses ac\nmain effect allocate heap.rgn\n'
        "main let okCode immutable ExitCode 0\n"
        "main allocateIn rgn buf OpaquePointer\nmain releaseRegion rgn\nmain do useIt\n"
        "main return okCode\n"
        "useIt is call\nuseIt in main\nuseIt invokes c.someUse\nuseIt arg p OpaquePointer buf\n"
        "useIt discards \"x\"\n"
    )
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(src)
    assert getattr(exc.value, "code", None) == "SS1561"


def test_region_double_release_rejected():
    # WS1-120 SS1565: releasing a region twice.
    src = (
        "Reg is project\nReg module appReg\nReg target console\nReg entry main\n"
        "appReg is module\nappReg path a.b\n"
        'appReg purpose "p"\nappReg invariant "i"\nExitCode is alias\nExitCode for Int32\n'
        "rgn is region\nrgn strategy arena\nrgn scope main\n"
        "ac is capability\nac grants allocate heap.rgn\n"
        "main is operation\nmain out ExitCode\nmain async no\n"
        'main purpose "p"\nmain invariant "i"\nmain uses ac\nmain effect allocate heap.rgn\n'
        "main let okCode immutable ExitCode 0\n"
        "main allocateIn rgn buf OpaquePointer\nmain releaseRegion rgn\nmain releaseRegion rgn\n"
        "main return okCode\n"
    )
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(src)
    assert getattr(exc.value, "code", None) == "SS1565"


def test_memory_safety_lint_rule_set_registered():
    # WS1-120: the memory-safety lint codes are all in the registry with a tier,
    # so doctor/explain can surface them. (SS1567 plain-value-owns is deferred —
    # it conflicts with the integer-fd handle convention in current eavc code.)
    for code in ("SS1560", "SS1561", "SS1562", "SS1563", "SS1564", "SS1565",
                 "SS1566", "SS1568", "SS1569", "SS1570", "SS1571"):
        assert code in eavc.DIAGNOSTICS, code
        assert eavc.DIAGNOSTICS[code]["tier"] in ("T0", "T1", "T2", "T3", "T4")


def test_region_missing_strategy_rejected():
    # WS1-120 SS1570: a region without a strategy.
    src = "rgn is region\nrgn scope main\n"
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(src)
    assert getattr(exc.value, "code", None) == "SS1570"


def test_view_missing_lifetime_rejected():
    # WS1-120 SS1571: a borrowed view that declares no lifetime.
    src = (
        "mk is operation\nmk out ExitCode\nmk async no\n"
        'mk purpose "p"\nmk invariant "i"\n'
        "mk in src Buffer\nmk let okCode immutable ExitCode 0\nmk do sl\nmk return okCode\n"
        "sl is call\nsl in mk\nsl invokes buffer.slice\nsl arg buffer Buffer src\n"
        "sl out win Slice\nsl borrows src\nsl mayEscape no\n"  # no `lifetime`
    )
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(src)
    assert getattr(exc.value, "code", None) == "SS1571"


def test_standard_memory_contract_and_impl():
    # WS1-118 / §8 §29 #14: the safe allocator API. The standard.memory sidecar
    # declares the Region/View/OwnedBuffer/AllocationFailure types and the
    # memory.openRegion/allocateIn/releaseRegion intrinsics (allocateIn returns a
    # View that borrows the region — a WS1-111 view); the in-language impl is the
    # `region` construct, which JIT-runs an open/allocate/release.
    prog = eavc.load_semsig(open(os.path.join(SIGS, "standard.memory.semsig"),
                                 encoding="utf-8").read())
    assert not any(d.severity == "error" for d in eavc.lint(prog))
    targets = {l.split("(")[0] for l in eavc.docs(prog)}
    for t in ("memory.openRegion", "memory.allocateIn", "memory.releaseRegion"):
        assert t in targets, t
    aliases = {a.name for a in prog.of_kind("alias")}
    assert {"Region", "View", "OwnedBuffer"} <= aliases
    assert any(e.name == "AllocationFailure" for e in prog.of_kind("error"))
    # allocateIn is a borrowing view (mayEscape no) per WS1-111
    alloc = prog.entities["memoryAllocateIn"]
    assert alloc.fact("borrows") and alloc.fact("lifetime")
    assert alloc.fact("mayEscape").payload[0] == "no"
    # the in-language impl (the region construct) JIT-runs allocate-many/free-once
    proc = subprocess.run(
        [sys.executable, os.path.join(HERE, "eavc.py"), "run", "-"],
        input=_ARENA_SRC, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr


_BUFFER_RUNTIME_SRC = (
    "Buf is project\nBuf module appBuf\nBuf target console\nBuf entry main\n"
    "appBuf is module\nappBuf path a.b\n"
    'appBuf purpose "p"\nappBuf invariant "i"\n'
    "ExitCode is alias\nExitCode for Int32\nBuffer is alias\nBuffer for OpaquePointer\n"
    "BufferBoundsError is error\n"
    "main is operation\nmain out ExitCode\nmain async no\n"
    'main purpose "p"\nmain invariant "i"\n'
    "main let cap immutable Int64 4\nmain let zero immutable Int64 0\n"
    "main let oobIndex immutable Int64 99\nmain let val immutable Byte 65\n"
    'main let oobMsg immutable String "oob"\n'
    "main let okCode immutable ExitCode 0\n"
    "main do makeBuf\nmain do put\nmain branch ifError put goto failed\n"
    "main do len\nmain do show\n"
    "main do getOob\nmain branch ifError getOob goto outOfBounds\n"
    "main return okCode\n"
    "main at failed return okCode\n"
    "main at outOfBounds do showOob\nmain return okCode\n"
    "makeBuf is call\nmakeBuf in main\nmakeBuf invokes buffer.create\n"
    "makeBuf arg size Int64 cap\nmakeBuf out buf Buffer\n"
    "put is call\nput in main\nput invokes buffer.set\n"
    "put arg buffer Buffer buf\nput arg index Int64 zero\nput arg value Byte val\n"
    "put out wrote Int32\nput catch e BufferBoundsError\n"
    "len is call\nlen in main\nlen invokes buffer.length\n"
    "len arg buffer Buffer buf\nlen out n Int64\n"
    "show is call\nshow in main\nshow invokes console.writeIntegerLine\nshow arg value Int64 n\n"
    "getOob is call\ngetOob in main\ngetOob invokes buffer.get\n"
    "getOob arg buffer Buffer buf\ngetOob arg index Int64 oobIndex\n"
    "getOob out byteVal Byte\ngetOob catch e2 BufferBoundsError\n"
    "showOob is call\nshowOob in main\nshowOob invokes console.writeLine\n"
    "showOob arg text String oobMsg\n"
)


def test_buffer_runtime_bounds_checked_jit_runs():
    # WS1-119: buffer.create/length/get/set JIT-run with real bounds checks — an
    # in-bounds length prints (4) and an out-of-bounds get takes the BufferBoundsError
    # branch (prints "oob"). No-op-failing: an ignored buffer.* would not lower to
    # the malloc + bounds-checked load/store this exercises.
    assert not any(d.severity == "error" for d in eavc.lint(eavc.parse(_BUFFER_RUNTIME_SRC)))
    proc = subprocess.run(
        [sys.executable, os.path.join(HERE, "eavc.py"), "run", "-"],
        input=_BUFFER_RUNTIME_SRC, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert "4" in proc.stdout      # buffer.length
    assert "oob" in proc.stdout    # the out-of-bounds get took the error branch


def test_label_undefined_target_rejected():
    # README ss17 #11: a goto target needs a matching `at` label.
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(
            "main is operation\nmain out ExitCode\nmain goto nowhere\n"
        )
    assert "has no `at nowhere`" in exc.value.message


def test_label_duplicate_rejected():
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(
            "main is operation\nmain out ExitCode\n"
            "main at dup return one\nmain at dup return two\n"
        )
    assert "duplicate label" in exc.value.message


def test_label_dead_warns():
    prog = eavc.parse(
        "main is operation\nmain out ExitCode\n"
        "main let okCode immutable ExitCode 0\n"
        "main at unused return okCode\nmain return okCode\n"
    )
    assert any("dead label" in w and "unused" in w for w in prog.warnings)


def test_catch_var_in_scope_at_iferror_target():
    # README §17 #9: the catch var is in scope at the ifError target.
    src = (
        "P is project\nP module m\nP target console\nP entry main\nm is module\nm path a.b\n"
        "main is operation\nmain out Int32\nmain effect write console.stdout\n"
        'main let t immutable String "hi"\nmain let zero immutable Int32 0\n'
        "main do w\nmain branch ifError w goto failed\nmain return zero\n"
        "main at failed do reportErr\nmain return zero\n"
        "w is call\nw in main\nw invokes console.writeLine\nw arg text String t\n"
        "w catch writeError ConsoleWriteError\n"
        "reportErr is call\nreportErr in main\nreportErr invokes console.writeIntegerLine\n"
        "reportErr arg value Int64 writeError\n"  # uses the catch var at the failed target
    )
    ir_text = _ir_for_source(src)  # lowers without an out-of-scope error
    assert "failed:" in ir_text


def test_iferror_requires_catch():
    # README ss13/ss17 #6: ifError needs a fallible call with a catch row.
    src = (
        "P is project\nP module m\nP target console\nP entry main\n"
        "m is module\nm path a.b\n"
        "main is operation\nmain out ExitCode\n"
        "main let okCode immutable ExitCode 0\n"
        "main do sumCall\nmain branch ifError sumCall goto failed\n"
        "main return okCode\nmain at failed return okCode\n"
        "sumCall is call\nsumCall in main\nsumCall invokes math.addInt64\n"
        "sumCall arg left Int64 okCode\nsumCall arg right Int64 okCode\n"
        "sumCall out total Int64\n"
    )
    with pytest.raises(eavc.EavError) as exc:
        eavc.lower_to_llvm(eavc.parse(src))
    assert "catch" in exc.value.message


def test_let_forward_reference_rejected():
    # README §12: a let may not forward-reference a later let.
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(
            "main is operation\nmain out ExitCode\n"
            "main let a immutable Int64 b\nmain let b immutable Int64 0\n"
        )
    assert exc.value.code == "SS1203"


def test_binding_no_shadow_rejected():
    # README ss17 #47: a let may not reuse a param or another let name.
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(
            "op is operation\nop in x Int64\nop out Int64\n"
            "op let x immutable Int64 1\nop return x\n"
        )
    assert "shadows" in exc.value.message
    with pytest.raises(eavc.EavError):
        eavc.parse(
            "op is operation\nop out Int64\n"
            "op let y immutable Int64 1\nop let y immutable Int64 2\nop return y\n"
        )


def test_record_new_missing_field_rejected():
    # README ss17 #49: construction-target args must cover the record's fields.
    src = (
        "P is project\nP module m\nP target console\nP entry main\nm is module\nm path a.b\n"
        "Point is record\nPoint field x Int64\nPoint field y Int64\n"
        "main is operation\nmain out ExitCode\n"
        "main let px immutable Int64 1\nmain let okCode immutable ExitCode 0\n"
        "main do build\nmain return okCode\n"
        "build is call\nbuild in main\nbuild invokes Point.new\n"
        "build arg x Int64 px\nbuild out p Point\n"  # missing field y
    )
    with pytest.raises(eavc.EavError) as exc:
        eavc.lower_to_llvm(eavc.parse(src))
    assert "missing field arg" in exc.value.message


def test_invokes_unresolved_bare_target_rejected():
    # README ss15: a bare invokes target must name an in-module operation.
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(
            "doThing is call\ndoThing in main\ndoThing invokes noSuchOp\n"
            "main is operation\nmain out ExitCode\n"
        )
    assert "unresolved bare target" in exc.value.message


def test_invokes_arg_name_mismatch_rejected():
    # README ss17 #49: arg slots must match the callee's `in` names.
    base = (
        "addTwo is operation\naddTwo in leftValue Int64\naddTwo in rightValue Int64\n"
        "addTwo out Int64\naddTwo do s\naddTwo return r\n"
        "s is call\ns in addTwo\ns invokes math.addInt64\n"
        "s arg left Int64 leftValue\ns arg right Int64 rightValue\ns out r Int64\n"
        "caller is operation\ncaller out Int64\n"
        "caller let one immutable Int64 1\ncaller do invokeAdd\ncaller return v\n"
        "invokeAdd is call\ninvokeAdd in caller\ninvokeAdd invokes addTwo\n"
    )
    with pytest.raises(eavc.EavError) as exc:  # wrong arg name
        eavc.parse(
            base
            + "invokeAdd arg wrongName Int64 one\ninvokeAdd arg rightValue Int64 one\n"
            "invokeAdd out v Int64\n"
        )
    assert "not an input of" in exc.value.message
    with pytest.raises(eavc.EavError):  # missing required arg
        eavc.parse(base + "invokeAdd arg leftValue Int64 one\ninvokeAdd out v Int64\n")


_CLEANUP_BASE = (
    "openDb is call\nopenDb in main\nopenDb invokes sqlite.openDatabase\n"
    "openDb arg path String dbPath\nopenDb out db Int64\nopenDb owns db\n"
    "openDb cleanedBy closeCleanup\n"
    "closeDb is call\ncloseDb in main\ncloseDb invokes sqlite.closeDatabase\n"
    "closeDb arg database Int64 db\ncloseDb catch closeErr SqliteCloseError\n"
)


def test_call_activated_more_than_once_rejected():
    # README ss17 #2: a call is activated exactly once.
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(
            "main is operation\nmain out ExitCode\n"
            'main let t immutable String "hi"\nmain do w\nmain do w\nmain return okCode\n'
            "main let okCode immutable ExitCode 0\n"
            "w is call\nw in main\nw invokes console.writeLine\nw arg text String t\n"
        )
    assert exc.value.code == "SS1702"


def test_cleanup_worker_also_do_activated_rejected():
    # README ss17 #43: a cleanup worker is not separately `do`-activated.
    src = _CLEANUP_BASE + (
        "closeCleanup is cleanup\ncloseCleanup in main\ncloseCleanup call closeDb\n"
        'closeCleanup because "x"\ncloseCleanup onFailure logAndSuppress\n'
        "closeCleanup cleans db\n"
        "main is operation\nmain out ExitCode\nmain let okCode immutable ExitCode 0\n"
        "main defer closeCleanup\nmain do closeDb\nmain return okCode\n"  # worker also do-activated
    )
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(src)
    assert exc.value.code == "SS1702"


def test_onfailure_propagate_needs_result():
    # README §15.6 / §29 #2: a propagating cleanup needs a Result-returning op.
    base = (
        "openDb is call\nopenDb in main\nopenDb invokes sqlite.openDatabase\n"
        "openDb out db Int64\nopenDb owns db\nopenDb cleanedBy closeCleanup\n"
        "closeDb is call\ncloseDb in main\ncloseDb invokes sqlite.closeDatabase\n"
        "closeDb arg database Int64 db\ncloseDb catch e SqliteCloseError\n"
        "closeCleanup is cleanup\ncloseCleanup in main\ncloseCleanup call closeDb\n"
        "closeCleanup onFailure propagate\ncloseCleanup cleans db\n"
    )
    main_body = (
        "main let okCode immutable ExitCode 0\n"
        "main do openDb\nmain defer closeCleanup\n"
    )
    # main returns a plain ExitCode -> nowhere to propagate
    bad = base + "main is operation\nmain out ExitCode\n" + main_body + "main return okCode\n"
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(bad)
    assert exc.value.code == "SS1518"
    # main returns Result -> ok (Result error slot matches the propagated worker
    # error type, per the WS2-053 replace rule)
    good = base + "main is operation\nmain out Result ExitCode SqliteCloseError\n" + main_body + "main return okCode nil\n"
    assert "main" in eavc.parse(good).entities


def test_cleanup_worker_out_without_catch_needs_discards():
    # README §17 #44: a cleanup worker with an out and no catch needs discards.
    src = (
        "openDb is call\nopenDb in main\nopenDb invokes sqlite.openDatabase\n"
        "openDb out db Int64\nopenDb owns db\nopenDb cleanedBy closeCleanup\n"
        "closeDb is call\ncloseDb in main\ncloseDb invokes sqlite.closeDatabase\n"
        "closeDb arg database Int64 db\ncloseDb out closeCount Int64\n"  # out, no catch/discards
        "closeCleanup is cleanup\ncloseCleanup in main\ncloseCleanup call closeDb\n"
        "closeCleanup cleans db\n"
    )
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(src)
    assert exc.value.code == "SS1544"


def test_cleanup_onfailure_needs_worker_catch():
    # README §17 #42: onFailure requires the worker call to have a catch.
    src = (
        "openDb is call\nopenDb in main\nopenDb invokes sqlite.openDatabase\n"
        "openDb out db Int64\nopenDb owns db\nopenDb cleanedBy closeCleanup\n"
        "closeNoCatch is call\ncloseNoCatch in main\ncloseNoCatch invokes sqlite.closeDatabase\n"
        "closeNoCatch arg database Int64 db\n"  # no catch
        "closeCleanup is cleanup\ncloseCleanup in main\ncloseCleanup call closeNoCatch\n"
        'closeCleanup onFailure logAndSuppress\ncloseCleanup because "x"\n'
        "closeCleanup cleans db\n"
    )
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(src)
    assert exc.value.code == "SS1542"


def test_ifvalue_emits_sugar_info():
    prog = eavc.parse(open(os.path.join(EXAMPLES, "ifvalue.sem"), encoding="utf-8").read())
    assert "SS1340" in {d.code for d in eavc.lint(prog)}


def test_cleanup_logandsuppress_requires_because():
    # README ss15.6 / ss17 #19.
    src = _CLEANUP_BASE + (
        "closeCleanup is cleanup\ncloseCleanup in main\ncloseCleanup call closeDb\n"
        "closeCleanup onFailure logAndSuppress\ncloseCleanup cleans db\n"
    )
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(src)
    assert "because" in exc.value.message


def test_cleanup_cleans_must_be_owned():
    src = (
        "closeDb is call\ncloseDb in main\ncloseDb invokes sqlite.closeDatabase\n"
        "closeDb arg database Int64 db\n"
        "closeCleanup is cleanup\ncloseCleanup in main\ncloseCleanup call closeDb\n"
        "closeCleanup cleans ghostResource\n"
    )
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(src)
    assert "no call `owns`" in exc.value.message


def test_owned_cleanup_must_be_deferred():
    # README §17 #16 (SS1502): an owned resource's cleanup must be deferred.
    src = (
        "openDb is call\nopenDb in main\nopenDb invokes sqlite.openDatabase\n"
        "openDb out db Int64\nopenDb owns db\nopenDb cleanedBy closeCleanup\n"
        "closeDb is call\ncloseDb in main\ncloseDb invokes sqlite.closeDatabase\n"
        "closeDb arg database Int64 db\ncloseDb catch e SqliteCloseError\n"
        "closeCleanup is cleanup\ncloseCleanup in main\ncloseCleanup call closeDb\n"
        "closeCleanup cleans db\n"
        "main is operation\nmain out ExitCode\nmain let okCode immutable ExitCode 0\n"
        "main do openDb\nmain return okCode\n"  # never defers closeCleanup
    )
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(src)
    assert exc.value.code == "SS1503"


def test_dangling_cleanedby_rejected():
    src = (
        "openDb is call\nopenDb in main\nopenDb invokes sqlite.openDatabase\n"
        "openDb out db Int64\nopenDb owns db\nopenDb cleanedBy noSuchCleanup\n"
    )
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(src)
    assert "dangling cleanedBy" in exc.value.message


def test_cleanup_well_formed_accepts():
    src = _CLEANUP_BASE + (
        "closeCleanup is cleanup\ncloseCleanup in main\ncloseCleanup call closeDb\n"
        "closeCleanup onFailure logAndSuppress\n"
        'closeCleanup because "db handle must close on every path"\n'
        "closeCleanup cleans db\n"
    )
    prog = eavc.parse(src)
    assert prog.entities["closeCleanup"].kind == "cleanup"


def test_dropped_nonvoid_result_rejected():
    # README ss17 #25: a dropped non-void result needs out/catch/discards.
    src = (
        "main is operation\nmain out ExitCode\n"
        "main let a immutable Int64 1\nmain let b immutable Int64 2\n"
        "main do sumCall\nmain return a\n"
        "sumCall is call\nsumCall in main\nsumCall invokes math.addInt64\n"
        "sumCall arg left Int64 a\nsumCall arg right Int64 b\n"  # no out/catch/discards
    )
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(src)
    assert "drops the non-void result" in exc.value.message


def test_dropped_result_with_discards_ok():
    src = (
        "main is operation\nmain out ExitCode\n"
        "main let a immutable Int64 1\nmain let b immutable Int64 2\n"
        "main do sumCall\nmain return a\n"
        "sumCall is call\nsumCall in main\nsumCall invokes math.addInt64\n"
        "sumCall arg left Int64 a\nsumCall arg right Int64 b\n"
        'sumCall discards "computed only for its (absent) side effect in this test"\n'
    )
    prog = eavc.parse(src)
    assert prog.entities["sumCall"].fact("discards") is not None


def test_void_console_write_needs_no_discards():
    # console.writeLine is void -> dropping its result is fine.
    src = (
        "main is operation\nmain out ExitCode\n"
        'main let t immutable String "hi"\nmain do w\nmain return t\n'
        "w is call\nw in main\nw invokes console.writeLine\nw arg text String t\n"
    )
    # return arity: main out ExitCode but returns t (String) — len 1, fine for
    # arity (type-check is separate); the point is no discards error is raised.
    prog = eavc.parse(src)
    assert prog.entities["w"].fact("discards") is None


def test_dotted_type_only_in_alias_for():
    # README §7/§17 #37: dotted type only valid in an alias `for` row.
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse("main is operation\nmain let x immutable api.Thing 0\n")
    assert exc.value.code == "SS3700"
    # alias `for` may be dotted (import-alias disambiguation, WS1-038)
    prog = eavc.parse("MyErr is alias\nMyErr for api.RequestError\n")
    assert prog.entities["MyErr"].fact("for").payload == ["api.RequestError"]


def test_owns_without_cleanedby_warns():
    src = (
        "openDb is call\nopenDb in main\nopenDb invokes sqlite.openDatabase\n"
        "openDb out db Int64\nopenDb owns db\n"  # owns, no cleanedBy
    )
    assert "SS3900" in {d.code for d in eavc.lint(eavc.parse(src))}


def test_entry_not_exported_warns():
    prog = eavc.parse(
        "P is project\nP module m\nP target console\nP entry main\nm is module\nm path a.b\n"
        "main is operation\nmain out ExitCode\n"  # m does not export main
    )
    assert "MD1013" in {d.code for d in eavc.lint(prog)}


def test_dotted_internal_reference_rejected():
    # README §3 / §17 #26: internal references are bare; dots are external-only.
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(
            "main is operation\nmain out ExitCode\nmain do foo.bar\n"
        )
    assert exc.value.code == "SS1326"


def test_activate_entity_not_owned_rejected():
    # README ss17 #4: do/start/defer must reference an in-op entity.
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(
            "other is operation\nother out ExitCode\n"
            "main is operation\nmain out ExitCode\nmain do helper\n"
            "helper is call\nhelper in other\nhelper invokes console.writeLine\n"
            "helper arg text String okText\n"
        )
    assert "owned by" in exc.value.message


def test_shared_catch_var_incompatible_types_warns():
    # README §25 / WS2-051: a catch var reused with incompatible error types warns.
    src = (
        "main is operation\nmain out ExitCode\nmain do callA\nmain do callB\n"
        "callA is call\ncallA in main\ncallA invokes x.a\ncallA catch e ErrorA\n"
        "callB is call\ncallB in main\ncallB invokes x.b\ncallB catch e ErrorB\n"
    )
    assert "SS2551" in {d.code for d in eavc.lint(eavc.parse(src))}


def test_uncovered_effect_warns():
    # README ss8 / ss17 #5: a declared effect with no covering `uses` warns.
    prog = eavc.parse(
        "main is operation\nmain out ExitCode\nmain effect write console.stdout\n"
    )
    assert any("not\n  covered" not in w and "not covered by a `uses`" in w
               for w in prog.warnings)


def test_effect_union_reports_call_level_gap():
    # WS2-040 / README §17 #5: an effect introduced by an activated call is part
    # of the op's effective effects and must be covered by the op's `uses`.
    src = (
        "dbReader is capability\ndbReader grants read database\n"
        "main is operation\nmain out ExitCode\nmain do queryCall\nmain return okCode\n"
        "main let okCode immutable ExitCode 0\n"
        "queryCall is call\nqueryCall in main\nqueryCall invokes sqlite.query\n"
        "queryCall effect read database\nqueryCall out rows Int64\n"
    )
    prog = eavc.parse(src)  # main `uses` nothing -> effective (read, database) uncovered
    assert any("read database" in w for w in prog.warnings)


def test_effect_coverage_transitive_call_graph():
    # WS2-041 / README §29 #10: an effect of a transitively-called user op is
    # part of the caller's effective effects and must be covered.
    src = (
        "main is operation\nmain out ExitCode\nmain do callHelper\nmain return okCode\n"
        "main let okCode immutable ExitCode 0\n"
        "callHelper is call\ncallHelper in main\ncallHelper invokes helper\n"
        "callHelper out r Int64\n"
        "helper is operation\nhelper out Int64\nhelper effect write network.socket\n"
        "helper let z immutable Int64 0\nhelper return z\n"
    )
    prog = eavc.parse(src)  # main neither declares nor `uses` the network effect
    assert any("write network.socket" in w and w.startswith("main") for w in prog.warnings)


def test_covered_effect_no_warning():
    prog = eavc.parse(
        "writer is capability\nwriter grants write console.stdout\n"
        "main is operation\nmain out ExitCode\nmain effect write console.stdout\n"
        "main uses writer\n"
    )
    assert not any("not covered by a `uses`" in w for w in prog.warnings)


def test_split_do_on_task_rejected():
    # README ss34.4: `do <task>` is a hard error — call/task/cleanup split.
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(
            "fetchThing is task\nfetchThing invokes some.thing\n"
            "main is operation\nmain out ExitCode\nmain do fetchThing\n"
        )
    assert "requires a call" in exc.value.message


def test_split_start_on_call_rejected():
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(
            "fetchThing is call\nfetchThing invokes some.thing\n"
            "main is operation\nmain out ExitCode\nmain async yes\n"
            "main start fetchThing\nmain join fetchThing\n"  # resolved; split is the issue
        )
    assert "requires a task" in exc.value.message


def test_split_defer_on_call_rejected():
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(
            "fetchThing is call\nfetchThing invokes some.thing\n"
            "main is operation\nmain out ExitCode\nmain defer fetchThing\n"
        )
    assert "requires a cleanup" in exc.value.message


# --------------------------------------------------------------------------
# End-to-end: parse -> lower to LLVM IR -> JIT run (the no-op-lowering-fails guard)
# --------------------------------------------------------------------------


def _eavc_run(name: str):
    proc = subprocess.run(
        [sys.executable, os.path.join(HERE, "eavc.py"), "run",
         os.path.join(EXAMPLES, name)],
        capture_output=True,
        text=True,
    )
    return proc


def test_e2e_hello_world_runs():
    proc = _eavc_run("hello_world.sem")
    assert proc.returncode == 0, proc.stderr
    assert "hello world" in proc.stdout


def test_e2e_add_two_runs():
    proc = _eavc_run("add_two.sem")
    assert proc.returncode == 0, proc.stderr
    assert "42" in proc.stdout


_HTTP_CODEC_MAIN = """
HttpRoundTrip is project
HttpRoundTrip module appHttpRoundTrip
HttpRoundTrip target console
HttpRoundTrip entry main

appHttpRoundTrip is module
appHttpRoundTrip path examples.httpRoundTrip
appHttpRoundTrip exports main
appHttpRoundTrip purpose "Exercise the standard.http url codec round-trip"
appHttpRoundTrip invariant "Prints the decoded value, equal to the original"

ExitCode is alias
ExitCode for Int32

main is operation
main out ExitCode
main async no
main purpose "URL-encode a component then decode it and print the round-tripped value"
main invariant "Prints the original text after an encode/decode round-trip"
main let original immutable String "a b&c=d"
main let okCode immutable ExitCode 0
main do encodeIt
main do decodeIt
main do showIt
main return okCode

encodeIt is call
encodeIt in main
encodeIt invokes urlEncode
encodeIt arg component String original
encodeIt out encoded String

decodeIt is call
decodeIt in main
decodeIt invokes urlDecode
decodeIt arg component String encoded
decodeIt out decoded String

showIt is call
showIt in main
showIt invokes console.writeLine
showIt arg text String decoded
"""


def test_listmap_semsig_contracts_load():
    # WS3-105 (deferred collections): the opaque-handle list/map contracts load.
    for mod, want in (("standard.list", "list.append("), ("standard.map", "map.size(")):
        prog = eavc.load_semsig(open(os.path.join(SIGS, mod + ".semsig"),
                                     encoding="utf-8").read())
        lines = eavc.docs(prog)
        assert any(l.startswith(want) for l in lines), (mod, want)


def test_list_pure_length_predicate_jit_runs():
    # WS3-105: the pure length predicate (no element storage) lowers + JIT-runs.
    stdlib = open(os.path.join(STD, "standard.list.sem"), encoding="utf-8").read()
    main = (
        "ListPred is project\nListPred module appListPred\n"
        "ListPred target console\nListPred entry main\n"
        "appListPred is module\nappListPred path examples.listPred\n"
        'appListPred exports main\nappListPred purpose "p"\nappListPred invariant "i"\n'
        "ExitCode is alias\nExitCode for Int32\n"
        "main is operation\nmain out ExitCode\nmain async no\n"
        'main purpose "p"\nmain invariant "i"\n'
        "main let len immutable Int64 0\nmain let okCode immutable ExitCode 0\n"
        "main do checkEmpty\nmain do show\nmain return okCode\n"
        "checkEmpty is call\ncheckEmpty in main\ncheckEmpty invokes listIsEmpty\n"
        "checkEmpty arg length Int64 len\ncheckEmpty out empty Bool\n"
        "show is call\nshow in main\nshow invokes console.writeIntegerLine\n"
        "show arg value Int64 empty\n"
    )
    proc = subprocess.run(
        [sys.executable, os.path.join(HERE, "eavc.py"), "run", "-"],
        input=stdlib + "\n" + main, capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "1"  # length 0 -> isEmpty true


def test_stdlib_parity_coverage_guard():
    # X-008: every EAV-sanctioned standard.* module has an EAVC catalog
    # (.semsig signature or .sem stdlib); semsc's libc-mirror modules are
    # explicitly outside the v0.3 sanctioned surface (§27 External surface).
    sanctioned = {
        "console", "math", "compare", "convert", "string", "assert", "test",
        "build", "html", "sqlite", "http",
        "process", "clock", "random", "net", "list", "map", "json",
    }
    semsc_only = {
        "bit", "bool", "bytes", "ctype", "numeric", "sort", "inttypes", "stdlib",
        "stdio", "log", "memory", "iso646", "errno", "constants", "limits",
        "stddef", "char", "buffer", "slice", "small_list", "array", "signal",
        "jwt", "bcrypt", "event", "document", "gui",
    }

    def has_catalog(module):
        return (os.path.exists(os.path.join(SIGS, f"standard.{module}.semsig"))
                or os.path.exists(os.path.join(STD, f"standard.{module}.sem")))

    missing = sorted(m for m in sanctioned if not has_catalog(m))
    assert not missing, f"sanctioned standard.* modules lacking a catalog: {missing}"
    # the two surfaces are disjoint — a module is sanctioned xor semsc-only
    assert not (sanctioned & semsc_only)


def test_json_semsig_contract_and_enum_discriminant():
    # WS3-106 (deferred codec): the json contract loads, and its value-kind enum
    # round-trips its discriminant in a type-directed position.
    prog = eavc.load_semsig(open(os.path.join(SIGS, "standard.json.semsig"),
                                 encoding="utf-8").read())
    lines = eavc.docs(prog)
    assert any(l.startswith("json.parse(") and "throws JsonAccessError" in l for l in lines)
    # JsonValueKind.numberJson has repr 2; a bare variant in a let lowers to it
    src = (
        "P is project\nP module m\nP target console\nP entry main\n"
        'm is module\nm path a.b\nm purpose "p"\nm invariant "i"\nm exports main\n'
        "ExitCode is alias\nExitCode for Int32\n"
        "JsonValueKind is enum\nJsonValueKind variant nullJson\n"
        "JsonValueKind variant numberJson\nJsonValueKind repr nullJson 0\n"
        "JsonValueKind repr numberJson 2\n"
        "main is operation\nmain out ExitCode\nmain async no\n"
        'main purpose "p"\nmain invariant "i"\n'
        "main let kind immutable JsonValueKind numberJson\n"
        "main let okCode immutable ExitCode 0\nmain do show\nmain return okCode\n"
        "show is call\nshow in main\nshow invokes console.writeIntegerLine\n"
        "show arg value Int64 kind\n"
    )
    proc = subprocess.run(
        [sys.executable, os.path.join(HERE, "eavc.py"), "run", "-"],
        input=src, capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "2"


def test_net_semsig_contract_loads():
    # WS3-104 (deferred runtime): the net contract loads and documents its surface.
    prog = eavc.load_semsig(open(os.path.join(SIGS, "standard.net.semsig"),
                                 encoding="utf-8").read())
    lines = eavc.docs(prog)
    assert any(l.startswith("net.connect(") and "throws NetError" in l for l in lines)
    assert any(l.startswith("net.send(") for l in lines)
    assert any(l.startswith("net.receive(") for l in lines)
    assert any(l.startswith("net.close(") for l in lines)


def test_http_stdlib_parses_lints_and_has_surface():
    # WS3-017: standard.http is an EAV-native runtimeBinding wrapper over the
    # eav_http_* runtime ABI (pure request/codec/session helpers).
    src = open(os.path.join(STD, "standard.http.sem"), encoding="utf-8").read()
    prog = eavc.parse(src)
    assert not any(d.severity == "error" for d in eavc.lint(prog))
    ops = {n for n in prog.order if prog.entities[n].kind == "operation"}
    surface = {
        "urlEncode", "urlDecode", "htmlEscape", "nowMillis", "sessionExpiresAt",
        "sessionIsExpired", "requestValueLength", "requestValueIsEmpty",
        "ensureDirectory",
    }
    assert surface.issubset(ops), surface - ops
    for n in ops:
        body = prog.entities[n].fact("body")
        assert body and body.payload[0] == "runtimeBinding"
        assert body.payload[1].startswith("eav_http_")


@pytest.mark.skipif(not _have_c_compiler(), reason="no C compiler to build the http runtime")
def test_e2e_http_url_codec_roundtrip_through_real_runtime():
    # WS3-017: compose standard.http with a driver main and JIT-run a URL
    # encode->decode round-trip against the real SemanticScript HTTP runtime
    # (built standalone from sem_http_runtime.c, no h2o). A no-op lowering or an
    # unlinked runtime cannot reproduce the original string.
    stdlib = open(os.path.join(STD, "standard.http.sem"), encoding="utf-8").read()
    composed = stdlib + "\n" + _HTTP_CODEC_MAIN
    proc = subprocess.run(
        [sys.executable, os.path.join(HERE, "eavc.py"), "run", "-"],
        input=composed, capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "a b&c=d"


def test_sqlite_stdlib_parses_lints_and_has_parity_surface():
    # WS3-016: standard.sqlite is an EAV-native runtimeBinding wrapper over the
    # eav_sqlite_* runtime ABI; it parses, lints clean, and covers the original
    # semsc.py surface (open/close/exec/prepare/step/bind/column/transactions).
    src = open(os.path.join(STD, "standard.sqlite.sem"), encoding="utf-8").read()
    prog = eavc.parse(src)
    assert not any(d.severity == "error" for d in eavc.lint(prog))
    ops = {n for n in prog.order if prog.entities[n].kind == "operation"}
    parity = {
        "openDatabase", "closeDatabase", "exec", "queryScalarInt64",
        "prepareStatement", "finalizeStatement", "resetStatement", "stepStatement",
        "bindInt64", "bindDouble", "bindText", "bindNull",
        "columnCount", "columnType", "columnName", "columnInt64", "columnDouble",
        "columnText", "columnByteCount", "lastInsertRowId", "changedRowCount",
        "beginImmediateTransaction", "commitTransaction", "rollbackTransaction",
        "enableWalMode", "errorMessage", "libraryVersion",
    }
    assert parity.issubset(ops), parity - ops
    # every operation binds an eav_sqlite_* runtime symbol (no compiler-owned sqlite)
    for n in ops:
        body = prog.entities[n].fact("body")
        assert body and body.payload[0] == "runtimeBinding"
        assert body.payload[1].startswith("eav_sqlite_")


@pytest.mark.skipif(not _have_c_compiler(), reason="no C compiler to build the sqlite runtime")
def test_e2e_sqlite_roundtrip_through_real_engine():
    # WS3-016 parity: compose the standard.sqlite stdlib with a driver main and
    # JIT-run a full round-trip against the vendored SQLite engine (built from
    # third_party/sqlite via the eav_sqlite shim). Open in-memory -> create ->
    # insert -> prepare -> step -> columnText -> print -> finalize -> close.
    # A no-op lowering (or an unlinked runtime) cannot produce "eav".
    stdlib = open(os.path.join(STD, "standard.sqlite.sem"), encoding="utf-8").read()
    composed = stdlib + "\n" + _SQLITE_ROUNDTRIP_MAIN
    proc = subprocess.run(
        [sys.executable, os.path.join(HERE, "eavc.py"), "run", "-"],
        input=composed, capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "eav"


def test_app_http_runtime_gauntlet_full_port():
    # X-044: the 27-op native-HTTP conformance harness is FULLY ported to the EAV
    # webServer entity (24 routes + 23 middleware), all handler ABIs validated,
    # routes exact-match-checked. Server *execution* (target webServer lowering)
    # is deferred (§27): the harness parses + lints clean but is not codegen'd.
    src = eavc.load_project(os.path.join(APPS, "http-runtime-gauntlet"))
    prog = eavc.parse(src)
    # op-count parity with the original v0.1 app (27 ops)
    assert len(prog.of_kind("operation")) == 27
    ws = prog.of_kind("webServer")
    assert len(ws) == 1
    server = ws[0]
    assert len(server.facts("route")) == 24       # route parity
    assert len(server.facts("middleware")) == 23   # middleware parity
    assert len(prog.of_kind("capability")) == 2    # capability parity
    # the full port lints clean — handler ABIs (SS2603) + route methods (SS2601)
    # + exact-match routes (SS2602) + effect coverage all pass, zero warnings
    diags = eavc.lint(prog)
    assert not [d.render() for d in diags if d.severity == "error"]
    assert not [d.render() for d in diags if d.severity != "error"]
    # the deferred server is gated at codegen, not lint
    with pytest.raises(eavc.EavError):
        eavc.lower_to_llvm(prog)


_DYNAMIC_ROUTE_SERVER = """
DynRoute is project
DynRoute module m
DynRoute target webServer
DynRoute entry srv
m is module
m path apps.dyn
m exports srv
m purpose "p"
m invariant "i"
respWriter is capability
respWriter grants write http.response
respWriter purpose "write responses"
srv is webServer
srv host "127.0.0.1"
srv port 8080
srv route GET "/api/todos/:id" showHandler
srv route POST "/api/todos/:id/complete" completeHandler
srv route GET "*" notFoundHandler
srv notFound notFoundHandler
showHandler is operation
showHandler in request HttpRequest
showHandler in response HttpResponse
showHandler out Int32
showHandler effect write http.response
showHandler uses respWriter
showHandler memory heap no
showHandler async no
showHandler purpose "p"
showHandler invariant "i"
showHandler let okCode immutable Int32 0
showHandler return okCode
completeHandler is operation
completeHandler in request HttpRequest
completeHandler in response HttpResponse
completeHandler out Int32
completeHandler effect write http.response
completeHandler uses respWriter
completeHandler memory heap no
completeHandler async no
completeHandler purpose "p"
completeHandler invariant "i"
completeHandler let okCode immutable Int32 0
completeHandler return okCode
notFoundHandler is operation
notFoundHandler in request HttpRequest
notFoundHandler in response HttpResponse
notFoundHandler out Int32
notFoundHandler effect write http.response
notFoundHandler uses respWriter
notFoundHandler memory heap no
notFoundHandler async no
notFoundHandler purpose "p"
notFoundHandler invariant "i"
notFoundHandler let okCode immutable Int32 0
notFoundHandler return okCode
"""


def test_webserver_dynamic_routing():
    # §14 dynamic routing (user-approved): `:name` route params and the `*`
    # catch-all are accepted (parse + lint; dispatch lowers with the deferred
    # target webServer codegen). A malformed `:` segment is SS2602.
    prog = eavc.parse(_DYNAMIC_ROUTE_SERVER)
    assert not [d.render() for d in eavc.lint(prog) if d.severity == "error"]
    server = prog.of_kind("webServer")[0]
    paths = [r.payload[1].strip('"') for r in server.facts("route") if len(r.payload) >= 2]
    assert "/api/todos/:id" in paths and "*" in paths
    # a `:` segment with no identifier is still rejected
    bad = _DYNAMIC_ROUTE_SERVER.replace('"/api/todos/:id"', '"/api/todos/:"')
    with pytest.raises(eavc.EavError) as exc:
        eavc.lint(eavc.parse(bad))
    assert getattr(exc.value, "code", None) == "SS2602"


def test_app_taskforge_web_project_layout():
    # X-043: taskforge-web uses the §28.2 build.sem + src/ layout — the project
    # manifest in build.sem, modules under src/ (root + components/ + pages/
    # submodule directories), a generated build.sem.lock.
    web = os.path.join(APPS, "taskforge-web")
    assert os.path.isfile(os.path.join(web, "build.sem"))
    assert os.path.isfile(os.path.join(web, "build.sem.lock"))
    for rel in ("src/main.sem", "src/components/main.sem", "src/pages/main.sem"):
        assert os.path.isfile(os.path.join(web, rel)), rel
    # build.sem owns the project; src/ modules carry no project entity (§28.2)
    build = eavc.parse(open(os.path.join(web, "build.sem"), encoding="utf-8").read())
    assert build.of_kind("project") and build.of_kind("project")[0].name == "TaskforgeWeb"
    # the two ported submodules lint clean on their own
    for sub in ("components", "pages"):
        prog = eavc.parse(open(os.path.join(web, "src", sub, "main.sem"),
                               encoding="utf-8").read())
        assert not [d.render() for d in eavc.lint(prog) if d.severity == "error"]


def test_app_taskforge_web_full_port():
    # X-043: the ENTIRE multi-module taskforge-web app is FULLY ported (no stubs):
    # the 18-op sqlite/bcrypt/json/session API module + 10 component render ops +
    # 3 server-rendered page handlers + the webServer entity routing all 16 routes,
    # in the §28.2 build.sem + src/ layout. Execution is deferred (target
    # webServer); the whole composed project parses + lints clean (0 diagnostics).
    web = os.path.join(APPS, "taskforge-web")
    prog = eavc.parse(eavc.load_project(web))

    # build.sem manifest: a no-entry webServer target whose entry is the server
    # entity (not an operation), and that entity is exported by its module (§28).
    build = eavc.parse(open(os.path.join(web, "build.sem"), encoding="utf-8").read())
    project = build.of_kind("project")[0]
    assert project.fact("target").payload[0] == "webServer"
    assert project.fact("entry").payload[0] == "taskForgeWebServer"
    assert "taskForgeWebServer" not in {o.name for o in prog.of_kind("operation")}

    # op-count parity with the untouched v0.1 app (18 main + 10 components + 3 pages)
    def _v1_ops(rel):
        path = os.path.join(V1_APPS, "taskforge-web", rel)
        return sum(1 for l in open(path, encoding="utf-8") if l.startswith("operation "))
    assert _v1_ops("main.sem") == 18
    assert (_v1_ops("main.sem") + _v1_ops("components/main.sem")
            + _v1_ops("pages/main.sem")) == 31
    assert len(prog.of_kind("operation")) == 31
    assert len(prog.of_kind("webServer")) == 1

    # route parity: same {method, path} set as the v0.1 source, including the §14
    # dynamic `:id`/`:filename` params and the `*` catch-all (404 fallback).
    ws = prog.of_kind("webServer")[0]
    port_routes = {(r.payload[0], r.payload[1].strip('"'))
                   for r in ws.rows if r.predicate == "route"}
    v1_routes = set()
    for line in open(os.path.join(V1_APPS, "taskforge-web", "main.sem"), encoding="utf-8"):
        t = line.split()
        if t[:1] == ["route"] and len(t) >= 4:
            v1_routes.add((t[2], t[3].strip('"')))
    assert port_routes == v1_routes
    assert len(port_routes) == 16
    assert ("GET", "*") in port_routes              # catch-all 404 (notFoundPageHandler)
    assert ("GET", "/api/todos/:id") in port_routes  # §14 dynamic path param

    # every route handler is a real operation with the (request, response) ABI,
    # resolved across the main/pages submodules (WS2-026 handler-ABI validation).
    for method, path in port_routes:
        handler_name = next(r.payload[2] for r in ws.rows if r.predicate == "route"
                            and r.payload[0] == method and r.payload[1].strip('"') == path)
        handler = prog.entities[handler_name]
        assert handler.kind == "operation", handler_name
        in_types = {p.payload[1] for p in handler.rows
                    if p.predicate == "in" and len(p.payload) >= 2}
        assert {"HttpRequest", "HttpResponse"} <= in_types, handler_name

    # the full composed project lints clean: 0 errors AND 0 warnings.
    diags = eavc.lint(prog)
    assert not [d.render() for d in diags if d.severity == "error"]
    assert not [d.render() for d in diags if d.severity != "error"]

    # the v0.1 source coexists untouched (still a SemanticScript module, no EAV rows)
    v1_text = open(os.path.join(V1_APPS, "taskforge-web", "main.sem"), encoding="utf-8").read()
    assert "webServer taskForgeWebServer" in v1_text  # original semsc keyword form
    assert " is webServer" not in v1_text             # not rewritten to EAV


def test_app_taskforge_tui_full_port():
    # X-042: the 24-op heap-array terminal todo app is FULLY ported (the keyboard
    # reader, ANSI control, buffer/JSON helpers, renderer + modal, scroll math,
    # JSON load/save, todo mutators, and the imperative `main` state machine using
    # the §12 `set` step). Execution is deferred (c.terminalReadKey + interactive
    # loop have no headless runtime); the whole app parses + lints clean.
    src = eavc.load_project(os.path.join(APPS, "taskforge-tui"))
    prog = eavc.parse(src)
    # op-count parity with the original v0.1 app (24 ops)
    assert len(prog.of_kind("operation")) == 24
    # the imperative state machine is expressed with the `set` step (README §12)
    set_rows = [r for op in prog.of_kind("operation") for r in op.rows
                if r.predicate == "set"]
    assert len(set_rows) >= 30  # main alone reassigns mutable state ~30+ times
    # the full port lints clean (c.*/pointer.* deferred as external targets)
    diags = eavc.lint(prog)
    assert not [d.render() for d in diags if d.severity == "error"]
    assert not [d.render() for d in diags if d.severity != "error"]


def test_app_taskforge_api_client_full_port():
    # X-041: the async outbound client is FULLY ported (the single main op, all
    # three net.fetchText fetches as tasks, record build + body read + release)
    # against sigs/standard.net.semsig and lints clean as `target console`;
    # network *execution* stays deferred (no net.* lowering).
    netsig = eavc.load_semsig(open(os.path.join(SIGS, "standard.net.semsig"),
                                   encoding="utf-8").read())
    net_targets = [l.split("(")[0] for l in eavc.docs(netsig)]
    assert "net.fetchText" in net_targets and "net.freeTextBody" in net_targets

    src = eavc.load_project(os.path.join(APPS, "taskforge-api-client"))
    prog = eavc.parse(src)
    # op-count parity with the original v0.1 app (1 op)
    assert [o.name for o in prog.of_kind("operation")] == ["main"]
    assert len(prog.of_kind("capability")) == 3   # capability parity
    # all three outbound fetches are started+joined tasks (the §20 async split)
    fetch_tasks = [t for t in prog.of_kind("task")
                   if (t.fact("invokes") and t.fact("invokes").payload
                       and t.fact("invokes").payload[0] == "net.fetchText")]
    assert len(fetch_tasks) == 3
    main = prog.entities["main"]
    fetch_names = {t.name for t in fetch_tasks}
    last_fetch_start = max(i for i, r in enumerate(main.rows)
                           if r.predicate == "start" and r.payload
                           and r.payload[0] in fetch_names)
    first_fetch_join = min(i for i, r in enumerate(main.rows)
                           if r.predicate == "join" and r.payload
                           and r.payload[0] in fetch_names)
    # every fetch is started before the first response is joined (async shape)
    assert last_fetch_start < first_fetch_join
    # the full port lints clean (net.* deferred as external targets)
    diags = eavc.lint(prog)
    assert not [d.render() for d in diags if d.severity == "error"]


def test_app_event_stream_smoke_full_port():
    # X-046: the standard.event smoke app is FULLY ported (all 4 ops, every
    # event.* call as a task) against sigs/standard.event.semsig and lints clean
    # as `target console`; event *execution* stays deferred (no event.* lowering).
    ev = eavc.load_semsig(open(os.path.join(SIGS, "standard.event.semsig"),
                               encoding="utf-8").read())
    ev_targets = [l.split("(")[0] for l in eavc.docs(ev)]
    for t in ("event.openProcessStream", "event.subscribeStream",
              "event.receiveEvent", "event.appendEvent", "event.acknowledgeEvent",
              "event.closeSubscription", "event.closeStream"):
        assert t in ev_targets, f"{t} missing from standard.event.semsig"

    src = eavc.load_project(os.path.join(APPS, "event-stream-smoke"))
    prog = eavc.parse(src)
    # op-count parity with the original v0.1 app (4 ops)
    ops = [o.name for o in prog.of_kind("operation")]
    assert ops == ["eventIdGreaterThan", "listenerOneHandleSmokeEvent",
                   "listenerTwoHandleSmokeEvent", "main"]
    assert len(prog.of_kind("capability")) == 12   # capability parity
    # every event.* call is a started+joined task (EAV async, the §20 split)
    tasks = prog.of_kind("task")
    assert len(tasks) == 17
    event_tasks = [t for t in tasks
                   if (t.fact("invokes") and t.fact("invokes").payload
                       and t.fact("invokes").payload[0].startswith("event."))]
    assert len(event_tasks) == 11   # open/2 subscribe/2 receive/append/2 ack/2 close + stream close
    # the full port lints clean (event.* deferred as external targets)
    diags = eavc.lint(prog)
    assert not [d.render() for d in diags if d.severity == "error"]


# X-047: app-port coverage matrix — every original app has an EAV port whose
# console-observable/README-sanctioned core runs (or is deferred per spec), the
# port lints clean, and the original v0.1 source coexists untouched.
_APP_PORT_MATRIX = {
    "html-template-lab": ("runs", []),
    "taskforge-api-client": ("deferred", []),
    "taskforge-tui": ("deferred", []),
    "taskforge-web": ("deferred", []),
    "http-runtime-gauntlet": ("deferred", []),
    "event-stream-smoke": ("deferred", []),
    "desktop-window-smoke": ("deferred", []),
}


def _v1_module_op_count(app):
    # Operations in the v0.1 source modules (excluding build.sem + *.test.sem),
    # i.e. the same surface the EAV port composes from src/.
    import glob
    n = 0
    for f in glob.glob(os.path.join(V1_APPS, app, "**", "*.sem"), recursive=True):
        base = os.path.basename(f)
        if base == "build.sem" or base.endswith(".test.sem"):
            continue
        n += sum(1 for l in open(f, encoding="utf-8") if l.startswith("operation "))
    return n


def _v1_route_count(app):
    import glob
    n = 0
    for f in glob.glob(os.path.join(V1_APPS, app, "**", "*.sem"), recursive=True):
        if os.path.basename(f).endswith(".test.sem"):
            continue
        n += sum(1 for l in open(f, encoding="utf-8") if l.startswith("route "))
    return n


def test_app_port_coverage_and_coexistence_guard():
    # X-047 (§28.8 / §29 #17): every EAV port is a 1:1 port — its op-count and
    # route-count match the v0.1 source exactly (a stub with fewer ops FAILS),
    # the composed project lints clean, the original v0.1 app coexists untouched,
    # and a deferred port records its deferral. (This guard previously certified
    # stubs; it is now exact.)
    for app, (status, stdlibs) in _APP_PORT_MATRIX.items():
        port_dir = os.path.join(APPS, app)
        assert os.path.isdir(port_dir), f"no EAV port for {app}"
        # coexistence: the original v0.1 app still exists, untouched
        assert os.path.isdir(os.path.join(V1_APPS, app)), f"original {app} missing"
        prog = eavc.parse(eavc.load_project(port_dir))
        # op-count parity with the v0.1 source (operations never split, §20)
        eav_ops = len(prog.of_kind("operation"))
        v1_ops = _v1_module_op_count(app)
        assert eav_ops == v1_ops, \
            f"{app}: op-count {eav_ops} != v0.1 {v1_ops} (stub / dropped ops?)"
        # route-count parity for webServer apps
        eav_routes = sum(len([r for r in ws.rows if r.predicate == "route"])
                         for ws in prog.of_kind("webServer"))
        assert eav_routes == _v1_route_count(app), \
            f"{app}: route-count {eav_routes} != v0.1 {_v1_route_count(app)}"
        # the composed project lints clean
        errs = [d.render() for d in eavc.lint(prog) if d.severity == "error"]
        assert not errs, f"{app} port regressed lint-clean: {errs}"
        if status == "deferred":
            assert os.path.exists(os.path.join(port_dir, "README.md")), \
                f"{app} deferral not recorded"


def test_app_port_parity_guard_rejects_a_stub():
    # The guard is exact, so a port that drops modules/operations FAILS it.
    # Reproduce the previously-rejected html-template-lab stub (the main module
    # alone, 1 op) and confirm it does not meet the v0.1 op-count (3 ops).
    import re
    v1_ops = _v1_module_op_count("html-template-lab")
    assert v1_ops == 3
    # the main module alone declares 1 operation (it even fails to parse on its
    # own — the cross-module page call is unresolved), well under the v0.1 count.
    main_text = open(os.path.join(APPS, "html-template-lab", "src", "main.sem"),
                     encoding="utf-8").read()
    stub_ops = len(re.findall(r"(?m)^\w+ is operation$", main_text))
    assert stub_ops < v1_ops  # a single-module stub fails op-count parity
    # the full multi-module port, by contrast, meets it
    full = eavc.parse(eavc.load_project(os.path.join(APPS, "html-template-lab")))
    assert len(full.of_kind("operation")) == v1_ops


def test_app_desktop_window_smoke_full_port():
    # X-045: the desktop GUI app is FULLY ported (all 4 ops, every gui.* call)
    # against sigs/standard.gui.semsig and lints clean as `target console`; GUI
    # *execution* stays deferred — `target windowsGui` hard-errors (SS0744).
    gui = eavc.load_semsig(open(os.path.join(SIGS, "standard.gui.semsig"),
                                encoding="utf-8").read())
    gui_targets = [l.split("(")[0] for l in eavc.docs(gui)]
    # the full surface the port invokes is recorded in the contract
    for t in ("gui.applicationCreate", "gui.windowCreate", "gui.controlOnEvent",
              "gui.listBoxAppendItem", "gui.textBoxText", "gui.applicationRun"):
        assert t in gui_targets, f"{t} missing from standard.gui.semsig"

    src = eavc.load_project(os.path.join(APPS, "desktop-window-smoke"))
    prog = eavc.parse(src)
    # op-count parity with the original v0.1 app (4 ops), and the call/task split
    ops = [o.name for o in prog.of_kind("operation")]
    assert ops == ["main", "appendGreetingFromInput",
                   "inspectSelectedGreeting", "clearGreetings"]
    assert len(prog.of_kind("storage")) == 19      # entity-count parity
    assert len(prog.of_kind("call")) == 31
    # every event handler is registered through a gui.controlOnEvent call
    on_event = [c for c in prog.of_kind("call")
                if (c.fact("invokes") and c.fact("invokes").payload
                    and c.fact("invokes").payload[0] == "gui.controlOnEvent")]
    assert len(on_event) == 4
    # the full port lints clean (gui.* deferred as external targets)
    diags = eavc.lint(prog)
    assert not [d.render() for d in diags if d.severity == "error"]

    # GUI execution stays deferred: a windowsGui target hard-errors (SS0744).
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(src.replace("DesktopWindowSmoke target console",
                               "DesktopWindowSmoke target windowsGui"))
    assert getattr(exc.value, "code", None) == "SS0744"


def test_app_html_template_lab_jit_runs():
    # X-040/X-047: the FULL 5-module port (main + shared + todo-domain +
    # todo-components + todo-pages) JIT-runs and prints the complete dashboard.
    # The page op calls the component op across modules and nests its rendered
    # HtmlFragment RAW (already-escaped markup is not double-escaped); the row
    # classes resolve through cross-module storage initializers.
    web = os.path.join(APPS, "html-template-lab")
    prog = eavc.parse(eavc.load_project(web))
    diags = eavc.lint(prog)
    assert not [d.render() for d in diags if d.severity == "error"]
    assert not [d.render() for d in diags if d.severity != "error"]
    # op-count parity with the v0.1 source (3 ops across the module graph)
    assert sorted(o.name for o in prog.of_kind("operation")) == [
        "main", "renderTodoDashboardPage", "renderTodoListFragment"]
    for rel in ("src/main.sem", "src/shared/main.sem", "src/todo-domain/main.sem",
                "src/todo-components/main.sem", "src/todo-pages/main.sem"):
        assert os.path.isfile(os.path.join(web, rel)), rel

    proc = subprocess.run(
        [sys.executable, os.path.join(HERE, "eavc.py"), "run", "-"],
        input=eavc.load_project(web), capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout
    assert "<!doctype html>" in out
    assert "<title>TaskForge TUI HTML Template Lab</title>" in out
    # the component fragment is nested RAW into the page (not double-escaped):
    assert '<section class="todo-list-region"' in out
    assert "&lt;section" not in out
    # all three todo-domain rows render, with cross-module-resolved row classes
    assert "Wire native webserver" in out
    assert "Split HTML rendering into modules" in out
    assert "Keep template inputs explicit" in out
    assert '<li class="todo-row todo-row-done">' in out   # firstTodoClassName -> shared.doneTodoClassName
    assert '<li class="todo-row todo-row-open">' in out    # second/third -> shared.openTodoClassName


@pytest.mark.skipif(not _have_c_compiler(), reason="no C compiler to build an exe")
def test_app_html_template_lab_builds_exe(tmp_path):
    # X-040: the port also compiles to a native exe that renders the document.
    src = eavc.load_project(os.path.join(APPS, "html-template-lab"))
    out = str(tmp_path / ("htmllab" + (".exe" if sys.platform == "win32" else "")))
    eavc.build_executable(eavc.parse(src), out)
    proc = subprocess.run([out], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert "<!doctype html>" in proc.stdout
    assert '<section class="todo-list-region"' in proc.stdout  # raw-nested fragment
    assert "Keep template inputs explicit" in proc.stdout      # third todo-domain row


@pytest.mark.skipif(not _have_c_compiler(), reason="no C compiler to build an exe")
def test_build_native_executable_runs(tmp_path):
    # The `build` command compiles a program to a native exe that runs standalone.
    out = str(tmp_path / ("hello" + (".exe" if sys.platform == "win32" else "")))
    prog = eavc.parse(open(os.path.join(EXAMPLES, "hello_world.sem"), encoding="utf-8").read())
    eavc.build_executable(prog, out)
    assert os.path.exists(out)
    proc = subprocess.run([out], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert "hello world" in proc.stdout


def test_e2e_runtime_binding_calls_libc_symbol():
    # README §11/§26: a `body runtimeBinding abs` op lowers to an extern named
    # after the bound symbol and is called directly; the JIT resolves libc `abs`
    # in-process, so abs(-7) == 7. A no-op lowering (or one that named the extern
    # after the op, leaving the symbol unresolved) could not produce 7.
    proc = _eavc_run("runtime_binding.sem")
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "7"


def test_runtime_binding_extern_named_after_symbol():
    # The extern is named after the bound ABI symbol, and a call targets it.
    ir_text = _ir_for("runtime_binding.sem")
    assert 'declare i32 @"abs"(i32' in ir_text
    assert 'call i32 @"abs"' in ir_text


def test_e2e_ifvalue_comparison_branch():
    # WS1-066: `branch ifValue X equals Y goto L` lowers to compare + branch.
    proc = _eavc_run("ifvalue.sem")
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "equal"


def test_ifvalue_lowers_to_icmp_branch():
    ir_text = _ir_for("ifvalue.sem")
    assert "icmp eq i64" in ir_text
    assert "br i1 " in ir_text


def test_e2e_compound_condition_sequential_guards():
    # README ss33.4: A AND B is two sequential guards (no and/or keyword).
    proc = _eavc_run("compound.sem")
    assert proc.returncode == 0, proc.stderr
    assert "both positive" in proc.stdout


def test_no_and_or_guard_keyword():
    # `and`/`or` are not guards; a branch using them is rejected.
    src = (
        "main is operation\nmain out ExitCode\n"
        "main let f immutable Bool true\nmain let okCode immutable ExitCode 0\n"
        "main branch and f goto done\nmain return okCode\nmain at done return okCode\n"
    )
    with pytest.raises(eavc.EavError):
        eavc.lower_to_llvm(eavc.parse(src))


def test_record_construction_and_access_lower():
    # README ss10.5: <Record>.new -> insertvalue; <Record>.<field> -> extractvalue.
    ir_text = _ir_for("record_demo.sem")
    assert "insertvalue {i64, i64} undef, i64 11, 0" in ir_text
    assert "insertvalue {i64, i64}" in ir_text
    assert "extractvalue {i64, i64}" in ir_text


def test_cyclic_module_storage_init_rejected():
    # README §30.2.1: module-storage init is a DAG; a cycle is a hard error.
    src = (
        "s1 is storage\ns1 scope module\ns1 type Int64\ns1 mutability immutable\ns1 value s2\n"
        "s2 is storage\ns2 scope module\ns2 type Int64\ns2 mutability immutable\ns2 value s1\n"
    )
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(src)
    assert exc.value.code == "SS3022"


def test_module_storage_init_dag_ok():
    src = (
        "base is storage\nbase scope module\nbase type Int64\nbase mutability immutable\nbase value 0\n"
        "derived is storage\nderived scope module\nderived type Int64\nderived mutability immutable\nderived value base\n"
    )
    assert "derived" in eavc.parse(src).entities


def test_module_storage_effectful_init_rejected():
    # README §30.2.1: a module-storage initializer must be effect-free.
    src = (
        "compute is operation\ncompute out Int64\n"
        "bad is storage\nbad scope module\nbad type Int64\n"
        "bad mutability immutable\nbad value compute\n"  # references an operation
    )
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(src)
    assert exc.value.code == "SS3021"


def test_module_storage_lowers_to_global():
    ir_text = _ir_for("module_storage.sem")
    assert '@"answerConstant" = internal constant i64 7' in ir_text
    assert 'load i64, i64* @"answerConstant"' in ir_text


def test_embed_literal_source_and_digest():
    # WS1-084: literalSource reads asset bytes; literalDigest verifies the hash.
    asset = os.path.join(HERE, "assets", "banner.txt")
    data = eavc.embed_literal_source(asset)
    assert data == b"EAV banner asset"
    eavc.embed_literal_source(asset, eavc.sha256_hex(data))  # matching digest ok
    with pytest.raises(eavc.EavError):
        eavc.embed_literal_source(asset, eavc.sha256_hex(b"tampered"))


def test_e2e_asset_embed_runs():
    proc = _eavc_run("asset_embed.sem")
    assert proc.returncode == 0, proc.stderr
    assert "EAV banner asset" in proc.stdout


def test_e2e_module_storage_runs():
    proc = _eavc_run("module_storage.sem")
    assert proc.returncode == 0, proc.stderr
    assert "7" in proc.stdout


def test_e2e_record_demo_runs():
    proc = _eavc_run("record_demo.sem")
    assert proc.returncode == 0, proc.stderr
    assert "11" in proc.stdout


def test_error_case_is_enum_equivalent_discriminant():
    # X-012 / README §9: error cases lower like enum variants (a discriminant).
    src = (
        "P is project\nP module m\nP target console\nm is module\nm path a.b\n"
        "ParseError is error\n"
        "BadJson is errorCase\nBadJson of ParseError\n"
        "Timeout is errorCase\nTimeout of ParseError\n"
        "makeErr is operation\nmakeErr out Int32\nmakeErr do mk\nmakeErr return e\n"
        "mk is call\nmk in makeErr\nmk invokes ParseError.Timeout\nmk out e Int32\n"
    )
    assert "ret i32 1" in _ir_for_source(src)  # Timeout is the 2nd case -> disc 1


def test_enum_variant_discriminant_lowers():
    # README ss10.5: a payloadless <Enum>.<variant> lowers to its discriminant.
    src = (
        "P is project\nP module m\nP target console\nP entry getDisc\n"
        "m is module\nm path a.b\n"
        "Mode is enum\nMode variant readOnly\nMode variant readWrite\n"
        "Mode repr readOnly 1\nMode repr readWrite 2\n"
        "getDisc is operation\ngetDisc out Int32\n"
        "getDisc do pick\ngetDisc return d\n"
        "pick is call\npick in getDisc\npick invokes Mode.readWrite\npick out d Int32\n"
    )
    ir_text = _ir_for_source(src)
    assert "ret i32 2" in ir_text  # readWrite's repr discriminant


def test_e2e_variant_match():
    # WS1-063: ifVariant narrows a payloadless enum by discriminant.
    proc = _eavc_run("variant_match.sem")
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "is done"


def test_e2e_operation_reference_indirect_call():
    # WS1-036/056: operationType binding invoked indirectly -> 42.
    proc = _eavc_run("operation_ref.sem")
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "42"


def test_operationtype_indirect_call_lowers():
    ir_text = _ir_for("operation_ref.sem")
    assert 'define i64 @"double"' in ir_text
    assert 'call i64 @"double"' in ir_text  # invoked through the Int64Endo binding


def test_e2e_factorial_recursion():
    # README ss33.3: direct recursion is permitted. factorial(5) == 120.
    proc = _eavc_run("factorial.sem")
    assert proc.returncode == 0, proc.stderr
    assert "120" in proc.stdout


def test_recursive_self_call_lowers():
    ir_text = _ir_for("factorial.sem")
    # the recursive call site targets the function itself
    assert 'call i64 @"factorial"' in ir_text


def test_builtin_targets_need_no_import():
    # README ss10.5: math/console/compare derived targets need no `imports` row.
    src = (
        "P is project\nP module m\nP target console\nP entry main\n"
        "m is module\nm path a.b\n"  # note: no imports rows at all
        "main is operation\nmain out ExitCode\nmain effect write console.stdout\n"
        "main let a immutable Int64 2\nmain let b immutable Int64 3\n"
        "main let okCode immutable ExitCode 0\n"
        "main do sumCall\nmain do writeIt\nmain return okCode\n"
        "sumCall is call\nsumCall in main\nsumCall invokes math.addInt64\n"
        "sumCall arg left Int64 a\nsumCall arg right Int64 b\nsumCall out s Int64\n"
        "writeIt is call\nwriteIt in main\nwriteIt invokes console.writeIntegerLine\n"
        "writeIt arg value Int64 s\n"
    )
    ir_text = _ir_for_source(src)
    assert "add i64" in ir_text
    assert 'call i32 (i8*, ...) @"printf"' in ir_text


def test_e2e_assert_and_test_and():
    # WS3-019/020: assert.equalInt64 -> Bool, folded by test.and; prints 1.
    proc = _eavc_run("assert_demo.sem")
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "1"


def test_assert_lowers_to_icmp_and_test_and():
    ir_text = _ir_for("assert_demo.sem")
    assert "icmp eq i64" in ir_text   # assert.equalInt64
    assert "and i1" in ir_text        # test.and


def test_e2e_string_concat():
    # WS3-015: string.concat via libc malloc/strlen/strcpy/strcat.
    proc = _eavc_run("string_concat.sem")
    assert proc.returncode == 0, proc.stderr
    assert "Hello, world" in proc.stdout


def test_string_concat_lowers_via_libc():
    ir_text = _ir_for("string_concat.sem")
    assert 'call i64 @"strlen"' in ir_text
    assert 'call i8* @"malloc"' in ir_text
    assert 'call i8* @"strcat"' in ir_text


def test_e2e_async_single_thread():
    # README §13: start eager, ifReady always taken -> task result printed.
    proc = _eavc_run("async_demo.sem")
    assert proc.returncode == 0, proc.stderr
    assert "42" in proc.stdout


def test_join_before_start_rejected():
    # README §15.5: a task lifecycle illegal transition — join before start.
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(
            "main is operation\nmain out ExitCode\nmain async yes\n"
            "main join t\nmain start t\n"
            "t is task\nt in main\nt invokes x.y\n"
        )
    assert exc.value.code == "SS1323"


def test_iferror_task_before_join_rejected():
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(
            "main is operation\nmain out ExitCode\nmain async yes\n"
            "main let okCode immutable ExitCode 0\n"
            "main start t\nmain branch ifError t goto failed\nmain join t\n"
            "main return okCode\nmain at failed return okCode\n"
            "t is task\nt in main\nt invokes x.y\nt catch e SomeError\n"
        )
    assert exc.value.code == "SS1324"


def test_started_task_must_be_resolved():
    # README §17 #20: a started task must be resolved before return.
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(
            "main is operation\nmain out ExitCode\nmain async yes\nmain start t\n"
            "t is task\nt in main\nt invokes x.y\n"
        )
    assert exc.value.code == "SS1320"


def test_cancel_needs_start():
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(
            "main is operation\nmain out ExitCode\nmain async yes\nmain cancel t\n"
            "t is task\nt in main\nt invokes x.y\n"
        )
    assert exc.value.code == "SS1321"


def test_ifcanceled_needs_cancel():
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(
            "main is operation\nmain out ExitCode\nmain async yes\n"
            "main start t\nmain join t\nmain branch ifCanceled t goto done\n"
            "main return okCode\nmain let okCode immutable ExitCode 0\n"
            "main at done return okCode\n"
            "t is task\nt in main\nt invokes x.y\n"
        )
    assert exc.value.code == "SS1322"


def test_start_in_async_no_operation_rejected():
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(
            "main is operation\nmain out ExitCode\nmain async no\nmain start t\n"
            "t is task\nt in main\nt invokes x.y\n"
        )
    assert exc.value.code == "SS1140"


def test_e2e_defer_reverse_order():
    # README §15.6/§33.8: defers run last-registered-first, after the body.
    proc = _eavc_run("defer_order.sem")
    assert proc.returncode == 0, proc.stderr
    lines = [l for l in proc.stdout.splitlines() if l.strip()]
    assert lines == ["work", "second", "first"]


def test_e2e_convert_widen_runs():
    # WS1-095/WS3-014: convert.toInt64 widens Int32 -> Int64 (sext).
    proc = _eavc_run("convert_demo.sem")
    assert proc.returncode == 0, proc.stderr
    assert "200" in proc.stdout


def test_convert_lowering_forms():
    assert "sext i32" in _ir_for("convert_demo.sem")
    src = (
        "P is project\nP module m\nP target console\nP entry conv\nm is module\nm path a.b\n"
        "conv is operation\nconv in n Int64\nconv out Float64\n"
        "conv do toF\nconv return f\n"
        "toF is call\ntoF in conv\ntoF invokes convert.toFloat64\n"
        "toF arg inputValue Int64 n\ntoF out f Float64\n"
    )
    assert "sitofp i64" in _ir_for_source(src)


def test_e2e_float_math_and_writefloatline():
    # WS3-011/013: math.addFloat64 + console.writeFloatLine. 1.5 + 2.5 == 4.
    proc = _eavc_run("float_math.sem")
    assert proc.returncode == 0, proc.stderr
    assert "4" in proc.stdout


def test_console_writers_lower_distinctly():
    # WS3-011: writeLine->puts, writeIntegerLine/writeFloatLine->printf with
    # the right format string.
    assert 'call i32 @"puts"' in _ir_for("hello_world.sem")
    assert "%lld" in _ir_for("add_two.sem")
    assert "%g" in _ir_for("float_math.sem")


def test_e2e_overflow_wraps_twos_complement():
    # README ss10.6: signed Int64 addition wraps. INT64_MAX + 1 == INT64_MIN.
    proc = _eavc_run("overflow.sem")
    assert proc.returncode == 0, proc.stderr
    assert "-9223372036854775808" in proc.stdout


def test_e2e_countdown_runs():
    proc = _eavc_run("countdown.sem")
    assert proc.returncode == 0, proc.stderr
    assert [ln for ln in proc.stdout.splitlines() if ln.strip()] == ["3", "2", "1"]


def test_noop_codegen_would_fail():
    """Guard: the e2e/IR tests are not vacuous.

    A no-op code generator (an empty module, or one that skips the `puts` call)
    would either lack `main` or not emit the program's instructions. We assert
    the real generator emits a verifiable module whose `main` actually calls the
    runtime — exactly what a stub cannot produce.
    """
    import llvmlite.binding as llvm

    eavc._ensure_native_init()
    ir_text = _ir_for("hello_world.sem")
    mod = llvm.parse_assembly(ir_text)
    mod.verify()
    assert mod.get_function("main").name == "main"
    assert 'call i32 @"puts"' in ir_text
    # An empty module (the no-op) has no `main` to run.
    empty = llvm.parse_assembly('target triple = "%s"' % llvm.get_default_triple())
    empty.verify()
    with pytest.raises(NameError):
        empty.get_function("main")
