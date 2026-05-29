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


def test_supply_chain_manifest_goldens_consistent():
    build = eavc.parse(open(os.path.join(MANIFESTS, "build.sem"), encoding="utf-8").read())
    lock = eavc.parse(open(os.path.join(MANIFESTS, "build.sem.lock"), encoding="utf-8").read())
    eavc.verify_supply_chain(build, lock)  # the goldens are consistent


SIGS = os.path.join(HERE, "sigs")


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
    # declared (extern), not defined with a body
    assert 'declare i64 @"cmp"(i64' in ir_text


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
        "main is operation\nmain out ExitCode\nmain do closeDb\nmain return okCode\n"
        "main let okCode immutable ExitCode 0\n"
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
    # main returns a plain ExitCode -> nowhere to propagate
    bad = base + "main is operation\nmain out ExitCode\n"
    with pytest.raises(eavc.EavError) as exc:
        eavc.parse(bad)
    assert exc.value.code == "SS1518"
    # main returns Result -> ok
    good = base + "main is operation\nmain out Result ExitCode SomeError\n"
    assert "main" in eavc.parse(good).entities


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


def test_module_storage_lowers_to_global():
    ir_text = _ir_for("module_storage.sem")
    assert '@"answerConstant" = internal constant i64 7' in ir_text
    assert 'load i64, i64* @"answerConstant"' in ir_text


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
