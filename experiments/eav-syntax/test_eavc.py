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


def test_parse_labeled_step_row():
    prog = eavc.parse(
        "main is operation\nmain at failed return code\n"
    )
    row = prog.entities["main"].rows[0]
    assert row.label == "failed"
    assert row.predicate == "return"
    assert row.payload == ["code"]


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


def test_lower_value_call_binds_value():
    v01 = _run_example("add_two.sem")
    assert "bind value answerValue Int64 answerCall" in v01
    assert "argument writeAnswer value Int64 answerValue" in v01


def test_lower_webserver_target_rejected():
    src = "W is project\nW module m\nW target webServer\nW entry s\n" "m is module\nm path a.b\n"
    with pytest.raises(eavc.EavError) as exc:
        eavc.lower_to_v01(eavc.parse(src))
    assert "console lowering" in exc.value.message


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
