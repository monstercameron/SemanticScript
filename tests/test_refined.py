"""Tests for the refined front end (semanticscript/compiler/refined).

Every rule is tested the same way: copy a worked example that checks clean,
introduce exactly one mistake, and assert the rule's code is reported. The
worked examples themselves must check clean, and the runnable ones must run.
"""
import os
import shutil
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "semanticscript", "compiler"))

from refined import check_path  # noqa: E402
from refined.diagnostics import CODES  # noqa: E402
from refined.shapes import grammar_markdown  # noqa: E402

EXAMPLES = os.path.join(ROOT, "docs", "refined-examples")
PROJECTS = ["hello", "sum", "factorial", "server", "selfhost"]


def _copy(tmp_path, project):
    dst = tmp_path / project
    shutil.copytree(os.path.join(EXAMPLES, project), dst)
    return dst


def _mutate(path, old, new):
    text = path.read_text(encoding="utf-8")
    assert text.count(old) == 1, f"expected exactly one {old!r} in {path.name}, found {text.count(old)}"
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text.replace(old, new))


def _codes(path):
    return [d.code for d in check_path(str(path)).diagnostics]


@pytest.mark.parametrize("project", PROJECTS)
def test_worked_examples_check_clean(project):
    res = check_path(os.path.join(EXAMPLES, project))
    assert res.ok, "\n".join(d.format() for d in res.diagnostics)


@pytest.mark.parametrize("project,expected", [("hello", "Hello, world!\n"), ("sum", "15\n"), ("factorial", "120\n")])
def test_runnable_examples_run(project, expected):
    proc = subprocess.run([sys.executable, os.path.join(ROOT, "semanticscript", "compiler", "refined"), "run",
                           os.path.join(EXAMPLES, project)], capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert proc.stdout == expected


def test_unsupported_features_are_refused_not_dropped():
    proc = subprocess.run([sys.executable, os.path.join(ROOT, "semanticscript", "compiler", "refined"), "run",
                           os.path.join(EXAMPLES, "server")], capture_output=True, text=True, timeout=120)
    assert proc.returncode == 1
    assert "R901" in proc.stdout


def test_every_code_has_a_summary_and_grammar_renders():
    assert all(CODES.values())
    md = grammar_markdown()
    assert "## `operation`" in md and "## `call`" in md


# (code, project, file, old text, new text): one mistake each.
CASES = [
    # lexical
    ("R101", "hello", "hello.sem", "main at begin do printGreeting\n", "main at begin do printGreeting \n"),
    ("R102", "hello", "hello.sem", '"Hello, world!"', '"Hello,\x01 world!"'),
    ("R104", "hello", "hello.sem", "printGreeting arg text String greeting lend", 'printGreeting arg text String gree"ting lend'),
    ("R105", "hello", "hello.sem", '"Hello, world!"', '"Hello\\q world!"'),
    ("R106", "hello", "hello.sem", '"Hello, world!"', '"Hello, world!'),
    # rows and entities
    ("R201", "hello", "hello.sem", "printGreeting catch printError console.WriteError\n",
     "printGreeting catch printError console.WriteError\nmain let stray immutable Int64 1\n"),
    ("R202", "hello", "hello.sem", "stdoutWriter is capability", "stdoutWriter is capabilty"),
    ("R203", "hello", "hello.sem", "stdoutWriter scope none\n",
     'stdoutWriter scope none\n\nstdoutWriter is capability\nstdoutWriter purpose "A second writer with the same name"\n'
     "stdoutWriter grants write console.stdout\nstdoutWriter scope none\n"),
    ("R204", "hello", "hello.sem", "printGreeting in main\n",
     'printGreeting invariant writes "A call cannot carry a tested claim"\nprintGreeting in main\n'),
    ("R205", "hello", "hello.sem", "main at succeeded return ok okCode", "main at succeeded retrun ok okCode"),
    ("R205", "hello", "hello.sem", "printGreeting invokes console.writeLine", "printGreeting invokes console.writeLine extra"),
    ("R205", "hello", "hello.sem", "main memory heap false", "main memory heap"),
    ("R206", "hello", "hello.sem", "main let okCode immutable ExitCode 0", "main let none immutable ExitCode 0"),
    ("R207", "sum", "sum.sem", "stdoutWriter is capability", "StdoutWriter is capability"),
    # skeleton
    ("R301", "hello", "hello.sem", "main memory heap false\nmain async false", "main async false\nmain memory heap false"),
    ("R302", "hello", "hello.sem", "main async false\n", ""),
    ("R302", "hello", "hello.sem", "printGreeting out none\n", "printGreeting out none\nprintGreeting out none\n"),
    ("R302", "hello", "hello.sem", "printGreeting arg text String greeting lend\n", ""),
    ("R303", "hello", "hello.sem", "main effect write console.stdout\n", "main effect write console.stdout\nmain effect none\n"),
    ("R304", "hello", "hello.sem", 'main purpose "Print a greeting and exit with code zero"', 'main purpose "main"'),
    ("R304", "server", "server.sem", "server exports main\n", "server exports main\nserver exports handleHealth\n"),
    ("R305", "hello", "hello.sem", "main label succeeded within none\n", ""),
    ("R306", "server", "server.sem", 'routes cell health path "/health"\n', ""),
    # names, types, signatures
    ("R401", "hello", "hello.sem", "invokes console.writeLine", "invokes console.writeLines"),
    ("R402", "hello", "hello.sem", "main at begin do printGreeting\n", "main at begin defer printGreeting\n"),
    ("R403", "hello", "hello.sem", "printGreeting arg text String greeting lend", "printGreeting arg text Int64 greeting lend"),
    ("R403", "sum", "sum.sem", "main at addStep set total newTotal", "main at addStep set total pastLast"),
    ("R404", "hello", "hello.sem", "hello imports standard.console\n", ""),
    ("R404", "hello", "hello.sem", "hello imports standard.console\n", "hello imports standard.console\nhello imports standard.math\n"),
    ("R405", "hello", "hello.sem", "printGreeting arg text String greeting lend", "printGreeting arg message String greeting lend"),
    ("R406", "hello", "hello.sem", "printGreeting arg text String greeting lend", "printGreeting arg text String greeting copy"),
    ("R406", "factorial", "mathdemo.sem", "factorial input n Int64 value", "factorial input n Int64 borrowed"),
    ("R407", "hello", "hello.sem", "main effect write console.stdout\n", "main effect none\n"),
    ("R407", "sum", "sum.sem", "main effect write console.stdout\n", "main effect write console.stdout\nmain effect read console.stdin\n"),
    ("R408", "hello", "hello.sem", "stdoutWriter grants write console.stdout", "stdoutWriter grants read console.stdin"),
    ("R408", "hello", "hello.sem", "main uses stdoutWriter", "main uses none"),
    ("R409", "hello", "hello.sem", "printGreeting ownedBy none", "printGreeting ownedBy main"),
    ("R409", "server", "server.sem", "readPath borrows request", "readPath borrows none"),
    ("R410", "hello", "hello.sem", "main async false", "main async true"),
    ("R410", "hello", "hello.sem", "main memory heap false", "main memory heap true"),
    ("R410", "factorial", "mathdemo.sem", "factorial maxRecursion 20", "factorial maxRecursion none"),
    ("R410", "server", "server.sem", "acceptConnection is task", "acceptConnection is call"),
    ("R411", "hello", "hello.sem", "main let okCode immutable ExitCode 0", "main let printGreeting immutable ExitCode 0"),
    # control flow
    ("R501", "sum", "sum.sem", "main at addStep goto sumLoop\n", ""),
    ("R501", "hello", "hello.sem", "main at succeeded return ok okCode\nmain at failed return ok failCode",
     "main at succeeded return ok okCode\nmain at failed return ok failCode\nmain at succeeded return ok okCode"),
    ("R502", "hello", "hello.sem", "goto failed else goto succeeded", "goto nowhere else goto succeeded"),
    ("R503", "sum", "sum.sem", "main label sumLoop maxIterations 5\n", ""),
    ("R503", "hello", "hello.sem", "main label begin within none\n", "main label begin within none\nmain label begin maxIterations 3\n"),
    ("R504", "sum", "sum.sem", "main at begin goto sumLoop", "main at begin goto addStep"),
    ("R504", "hello", "hello.sem", "main at succeeded return ok okCode", "main at succeeded goto begin"),
    ("R505", "sum", "sum.sem", "main at addStep set nextNumber afterNextNumber\n", ""),
    ("R506", "hello", "hello.sem", "main at begin branch ifError printGreeting goto failed else goto succeeded",
     "main at begin goto succeeded"),
    ("R507", "sum", "sum.sem", "main let total mutable Int64 0", "main let total mutable Int64 unset"),
    ("R508", "hello", "hello.sem", "main at failed return ok failCode", "main at failed return ok none"),
    ("R508", "hello", "hello.sem", "main at failed return ok failCode", "main at failed return error failCode"),
    ("R509", "selfhost", "compiler/tokens.sem", "firstKind at failed case LexError.unexpectedByte bind badOffset Int64 goto missing",
     "firstKind at failed case LexError.unexpectedByte bind none none goto missing"),
    ("R510", "hello", "hello.sem", "main at begin do printGreeting\n", "main at begin do printGreeting\nmain at begin do printGreeting\n"),
    ("R511", "hello", "hello.sem", "main at failed return ok failCode",
     "main at failed return ok failCode\nmain at orphan return ok failCode"),
    ("R512", "server", "server.sem", "main at listenFailed join connections\n", ""),
    # ownership on every path, borrows, exclusive loans (LR-20, LR-31)
    ("R513", "server", "server.sem", "main at listening defer closeListenerCleanup\n", ""),
    ("R513", "server", "server.sem", "acceptConnection arg listener net.TcpListener listener lend",
     "acceptConnection arg listener net.TcpListener listener give"),
    ("R514", "server", "server.sem", "readPath arg record http.HttpRequest request lend",
     "readPath arg record http.HttpRequest request give"),
    ("R515", "server", "server.sem", "readMethod arg record http.HttpRequest request lend",
     "readMethod arg record http.HttpRequest request lendMutable"),
    # counted loops (A14)
    ("R505", "sum", "sum.sem", "main label sumLoop maxIterations 5", "main label sumLoop maxIterations 6"),
    ("R505", "sum", "sum.sem", "addOne invokes math.addInt64", "addOne invokes math.subtractInt64"),
    ("R505", "sum", "sum.sem", "pastLastCheck invokes compare.greaterThanInt64", "pastLastCheck invokes compare.equalInt64"),
    # capability scopes (LR-34 rule 5)
    ("R408", "server", "server.sem", "main let port immutable Int32 8080", "main let port immutable Int32 9090"),
    ("R408", "server", "server.sem", 'listenAuthority scope "0.0.0.0:8080"', "listenAuthority scope none"),
    ("R408", "server", "server.sem", "connectionIo scope none", 'connectionIo scope "anything"'),
    # invariant coverage (LR-06 rule 3)
    ("R604", "factorial", "mathdemo.test.sem", "fiveFactorialTest verifies factorial fiveFactorial",
     "fiveFactorialTest verifies main fiveFactorial"),
    ("R604", "hello", "hello.test.sem", "greetingTest typeParam none", "greetingTest typeParam T plain"),
    # project
    ("R601", "hello", "build.sem", "hello entry hello.main", "hello entry hello.printGreeting"),
    ("R602", "hello", "hello.sem", "hello path hello", "hello path greeting"),
    ("R603", "selfhost", "compiler/lexer.sem", "lexer imports standard.compare\n",
     "lexer imports standard.compare\nlexer imports compiler.tokens\n"),
    ("R604", "selfhost", "compiler/tokens.test.sem", "verifies tokenize emptyGivesNoTokens", "verifies tokenize noSuchClaim"),
]


@pytest.mark.parametrize("code,project,file,old,new", CASES,
                         ids=[f"{c[0]}-{i}" for i, c in enumerate(CASES)])
def test_rule_fires(tmp_path, code, project, file, old, new):
    d = _copy(tmp_path, project)
    _mutate(d / file, old, new)
    got = _codes(d)
    assert code in got, f"{code} not reported; got {sorted(set(got))}"


GENERIC_BUILD = """generics is project
generics purpose "Exercise generic operations and record updates"
generics target library
generics module gen
generics entry none
"""

GENERIC_MODULE = """gen is module
gen purpose "Generic operations and record updates for the checker tests"
gen path gen
gen imports none
gen exports none

Point is record
Point purpose "A position on a line and how heavy it is"
Point typeParam none
Point field position Int64
Point field weight Int64

pick is operation
pick purpose "Return the first value when asked to, otherwise the second"
pick invariant none
pick typeParam T plain
pick input chooseFirst Bool value
pick input first T value
pick input second T value
pick output T
pick outputOwner none
pick raises none
pick effect none
pick uses none
pick memory heap false
pick async false
pick maxRecursion none
pick label begin loopKind none
pick label begin within none
pick label takeFirst loopKind none
pick label takeFirst within none
pick label takeSecond loopKind none
pick label takeSecond within none
pick at begin branch if chooseFirst goto takeFirst else goto takeSecond
pick at takeFirst return ok first
pick at takeSecond return ok second

pickInt is operationInstance
pickInt purpose "Pick between two whole numbers"
pickInt instantiates pick Int64

useBoth is operation
useBoth purpose "Pick a position and move a point there"
useBoth invariant none
useBoth typeParam none
useBoth input none
useBoth output Point
useBoth outputOwner none
useBoth raises none
useBoth effect none
useBoth uses none
useBoth memory heap false
useBoth async false
useBoth maxRecursion none
useBoth label begin loopKind none
useBoth label begin within none
useBoth let yes immutable Bool true
useBoth let one immutable Int64 1
useBoth let two immutable Int64 2
useBoth at begin do choose
useBoth at begin do makePoint
useBoth at begin do movePoint
useBoth at begin return ok moved

choose is call
choose in useBoth
choose invokes pickInt
choose arg chooseFirst Bool yes copy
choose arg first Int64 one copy
choose arg second Int64 two copy
choose out chosen Int64
choose ownedBy none
choose cleanedBy none
choose borrows none
choose catch none

makePoint is call
makePoint in useBoth
makePoint invokes Point.new
makePoint arg position Int64 one copy
makePoint arg weight Int64 two copy
makePoint out point Point
makePoint ownedBy none
makePoint cleanedBy none
makePoint borrows none
makePoint catch none

movePoint is call
movePoint in useBoth
movePoint invokes Point.with
movePoint arg record Point point copy
movePoint arg position Int64 chosen copy
movePoint out moved Point
movePoint ownedBy none
movePoint cleanedBy none
movePoint borrows none
movePoint catch none
"""


def _generic_project(tmp_path, old=None, new=None):
    d = tmp_path / "generics"
    d.mkdir()
    (d / "build.sem").write_text(GENERIC_BUILD, encoding="utf-8")
    text = GENERIC_MODULE if old is None else GENERIC_MODULE.replace(old, new)
    assert old is None or GENERIC_MODULE.count(old) == 1
    with open(d / "gen.sem", "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    return d


def test_generic_operations_and_record_with_check_clean(tmp_path):
    res = check_path(str(_generic_project(tmp_path)))
    assert res.ok, "\n".join(d.format() for d in res.diagnostics)


@pytest.mark.parametrize("code,old,new", [
    ("R402", "choose invokes pickInt", "choose invokes pick"),
    ("R403", "pickInt instantiates pick Int64", "pickInt instantiates pick String"),
    ("R405", "movePoint arg position Int64 chosen copy", "movePoint arg place Int64 chosen copy"),
])
def test_generic_rules_fire(tmp_path, code, old, new):
    got = _codes(_generic_project(tmp_path, old, new))
    assert code in got, f"{code} not reported; got {sorted(set(got))}"


def test_stale_flags_structure_change_without_prose_change(tmp_path):
    import shutil as sh
    d = tmp_path / "repo"
    sh.copytree(os.path.join(EXAMPLES, "hello"), d / "hello")

    def git(*a):
        subprocess.run(["git", *a], cwd=d, check=True, capture_output=True)
    git("init", "-q")
    git("-c", "user.email=t@example.invalid", "-c", "user.name=t", "add", "-A")
    git("-c", "user.email=t@example.invalid", "-c", "user.name=t", "commit", "-q", "-m", "base")
    _mutate(d / "hello" / "hello.sem", 'main let greeting immutable String "Hello, world!"',
            'main let greeting immutable String "Goodbye, world!"')
    from refined.stale import stale
    found = stale(str(d / "hello"), "HEAD")
    assert [x.code for x in found] == ["R605"] and "`main`" in found[0].message
    _mutate(d / "hello" / "hello.sem", 'main purpose "Print a greeting and exit with code zero"',
            'main purpose "Print a farewell and exit with code zero"')
    assert stale(str(d / "hello"), "HEAD") == []


def _refined(*args, timeout=300):
    return subprocess.run([sys.executable, os.path.join(ROOT, "semanticscript", "compiler", "refined"), *args],
                          capture_output=True, text=True, timeout=timeout)


@pytest.mark.parametrize("project,count", [("hello", 1), ("factorial", 1), ("selfhost", 5)])
def test_example_tests_pass_on_the_backend(project, count):
    proc = _refined("test", os.path.join(EXAMPLES, project))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert f"{count} of {count} tests passed" in proc.stdout


def test_backend_reports_failures_and_traps(tmp_path):
    d = _copy(tmp_path, "selfhost")
    _mutate(d / "compiler" / "tokens.test.sem", "badByteTest let expectedOffset immutable Int64 3",
            "badByteTest let expectedOffset immutable Int64 2")
    _mutate(d / "compiler" / "lexer.test.sem", 'scanWordTest let source immutable String "abc def"',
            'scanWordTest let source immutable String "abcdefgh"')
    _mutate(d / "compiler" / "lexer.sem", "scanWord label advance maxIterations sourceLength",
            "scanWord label advance maxIterations three")
    _mutate(d / "compiler" / "lexer.sem", "scanWord let one immutable Int64 1",
            "scanWord let one immutable Int64 1\nscanWord let three immutable Int64 3")
    proc = _refined("test", str(d))
    assert proc.returncode == 1
    assert "FAIL        tokens.badByteTest" in proc.stdout and "expected 2, got 3" in proc.stdout
    assert "TRAPPED     lexer.scanWordTest" in proc.stdout and "maxIterations three" in proc.stdout


def test_run_json_captures_output():
    import json
    proc = _refined("run", os.path.join(EXAMPLES, "sum"), "--json")
    assert proc.returncode == 0
    payload = json.loads(proc.stdout)
    assert payload["stdout"] == "15\n" and payload["exitCode"] == 0


def test_every_rule_code_is_exercised():
    tested = {c[0] for c in CASES} | {"R605"}
    untested = sorted(set(CODES) - tested - {"R901"})
    assert not untested, f"codes with no failing-program test: {untested}"
