"""Tests for the EAV-Steps front end (eavc.py).

Project rule (todos.md scope rule): no item is "done" without a test that would
fail under a no-op lowering. The end-to-end tests here run lowered programs
through the real reference compiler and assert on stdout + exit code, so a
stubbed/no-op lowering makes them red.

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


def _run_example(name: str):
    program = eavc.parse(open(os.path.join(EXAMPLES, name), encoding="utf-8").read())
    v01 = eavc.lower_to_v01(program)
    return v01


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
        "main is operation\nmain at failed return code\n"
    )
    row = prog.entities["main"].rows[0]
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
    # README ss10: Byte is a primitive synonym for UInt8.
    src = (
        "P is project\nP module m\nP target console\nP entry main\n"
        "m is module\nm path a.b\n"
        "R is record\nR field flags Byte\n"
        "main is operation\nmain out ExitCode\n"
        "main let mask immutable Byte 7\nmain let okCode immutable ExitCode 0\nmain return okCode\n"
    )
    v01 = eavc.lower_to_v01(eavc.parse(src))
    assert "storage local immutable mask UInt8 7" in v01
    assert "field R flags UInt8" in v01
    assert "Byte" not in v01


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


def test_float_literal_accepts():
    prog = eavc.parse("main is operation\nmain let r immutable Float64 1.5\n")
    assert prog.entities["main"].fact("let").payload[3] == "1.5"


@pytest.mark.parametrize("bad", [".5", "5.", "1.2.3"])
def test_float_literal_rejects(bad):
    # README ss2: no leading/trailing dot.
    with pytest.raises(eavc.EavError):
        eavc.parse(f"main is operation\nmain let r immutable Float64 {bad}\n")


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
# Lowering (README ss18) — structural assertions
# --------------------------------------------------------------------------


def test_lower_hello_world_key_rows():
    v01 = _run_example("hello_world.sem")
    assert "project HelloWorld" in v01
    assert "entry console main" in v01
    assert "errorCase ConsoleWriteError ConsoleWriteFailed Int32" in v01
    assert "capability stdoutWriter console.stdout write" in v01
    assert "useCapability main stdoutWriter" in v01
    assert "call writeHello console.writeLine" in v01
    assert "argument writeHello text String helloText" in v01
    assert "ignore void source writeHello" in v01
    assert "bind error writeError ConsoleWriteError writeHello" in v01
    assert "branch error source writeHello target failed" in v01
    assert "label failed" in v01


def test_lower_capability_grants_resource_action_order():
    # EAV `grants <action> <resource>` -> v0.1 `capability NAME <resource> <action>`
    v01 = _run_example("hello_world.sem")
    assert "capability stdoutWriter console.stdout write" in v01


def test_operation_decl_rows_reorder_stable():
    # README ss11: operation declaration rows are order-independent; only `in`
    # order is significant. Lowering must be identical when decls are shuffled.
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
    assert eavc.lower_to_v01(eavc.parse(a)) == eavc.lower_to_v01(eavc.parse(b))


def test_lower_value_call_binds_value():
    v01 = _run_example("add_two.sem")
    assert "bind value answerValue Int64 answerCall" in v01
    assert "argument writeAnswer value Int64 answerValue" in v01


def test_lower_error_cases_and_void_payload():
    # README ss9: errorCase `of`/`payload`; a Void payload carries no data.
    src = (
        "P is project\nP module m\nP target console\nP entry main\n"
        "m is module\nm path a.b\n"
        "E is error\n"
        "Failed is errorCase\nFailed of E\nFailed payload Int32\n"
        "Closed is errorCase\nClosed of E\nClosed payload Void\n"
        "main is operation\nmain out ExitCode\n"
        "main let okCode immutable ExitCode 0\nmain return okCode\n"
    )
    v01 = eavc.lower_to_v01(eavc.parse(src))
    assert "error E" in v01
    assert "errorCase E Failed Int32" in v01
    assert "errorCase E Closed" in v01
    assert "errorCase E Closed Void" not in v01


def test_lower_webserver_target_rejected():
    src = "W is project\nW module m\nW target webServer\nW entry s\n" "m is module\nm path a.b\n"
    with pytest.raises(eavc.EavError) as exc:
        eavc.lower_to_v01(eavc.parse(src))
    assert "console lowering" in exc.value.message


def test_lower_mutable_rebind_uses_set_storage():
    # README ss12: `out` to a `let mutable` rebinds via bind-to-temp + set storage.
    v01 = _run_example("countdown.sem")
    assert "storage local mutable counter Int64 3" in v01
    assert "set storage counter " in v01
    # the rebind binds a fresh temp, not the mutable name directly
    assert "bind value counter Int64 decrementCounter" not in v01


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
        eavc.lower_to_v01(eavc.parse(src))
    assert "immutable" in exc.value.message


def test_lower_branch_iffalse_inverts():
    # README ss13: `branch ifFalse COND goto L` inverts to a true-taken skip.
    v01 = _run_example("countdown.sem")
    assert "branch if condition shouldContinue target ifFalseSkip" in v01
    assert "jump target loopExit" in v01


def test_lower_do_on_task_rejected():
    # README ss34.4: `do <task>` is a hard error — call/task/cleanup split.
    src = (
        "P is project\nP module m\nP target console\nP entry main\n"
        "m is module\nm path a.b\n"
        "t is task\nt invokes some.thing\n"
        "main is operation\nmain out ExitCode\nmain do t\n"
    )
    with pytest.raises(eavc.EavError) as exc:
        eavc.lower_to_v01(eavc.parse(src))
    assert "task" in exc.value.message


# --------------------------------------------------------------------------
# End-to-end: parse -> lower -> compile -> run (the no-op-lowering-fails guard)
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


def test_e2e_countdown_runs():
    proc = _eavc_run("countdown.sem")
    assert proc.returncode == 0, proc.stderr
    assert [ln for ln in proc.stdout.splitlines() if ln.strip()] == ["3", "2", "1"]


def test_noop_lowering_would_fail():
    """Guard: feeding raw EAV (a no-op 'lowering') to the compiler must fail.

    This proves the e2e tests above are not vacuous — the program only runs
    because lower_to_v01 produces real v0.1 source, not because the compiler
    happens to accept EAV text.
    """
    raw_eav = open(os.path.join(EXAMPLES, "hello_world.sem"), encoding="utf-8").read()
    import tempfile

    with tempfile.NamedTemporaryFile(
        "w", suffix=".sscript", delete=False, encoding="utf-8"
    ) as tf:
        tf.write(raw_eav)
        tmp = tf.name
    try:
        proc = subprocess.run(
            [sys.executable, eavc._semsc_path(), tmp, "--run"],
            capture_output=True,
            text=True,
        )
        assert proc.returncode != 0 or "hello world" not in proc.stdout
    finally:
        os.unlink(tmp)
