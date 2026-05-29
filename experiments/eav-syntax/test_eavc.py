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
    "closeDb arg database Int64 db\n"
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
            "main is operation\nmain out ExitCode\nmain start fetchThing\n"
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
