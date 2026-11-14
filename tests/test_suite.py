"""The language test suite (tests/suite): positive, negative, and edge cases.

- Program cases (`tests/suite/programs`): whole programs whose header comments
  state what they cover and what must happen (check, run, trap, test).
- Mutations (`tests/suite/mutations.py`): one mistake in a passing case and the
  exact set of rule codes it must produce.
- Generated tests: stress (sizes far beyond hand-written code), fuzz (random
  damage never crashes the checker), differential (random arithmetic agrees
  with a Python model, traps included), determinism, and source locations.
- The coverage map (`docs/test-suite.md`) must match the evidence here.
"""
from __future__ import annotations

import json
import os
import random
import shutil
import sys

import pytest

SUITE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "suite")
sys.path.insert(0, SUITE)

import caselib  # noqa: E402
import coverage_map  # noqa: E402
import sembuild as sb  # noqa: E402
from caselib import allows_rows  # noqa: E402
from mutations import MUTATIONS  # noqa: E402
from refined.diagnostics import CODES  # noqa: E402

CASES = caselib.discover()
CASE_BY_NAME = {c.name: c for c in CASES}
INT64_MIN, INT64_MAX = -(1 << 63), (1 << 63) - 1


# ---------------------------------------------------------------- program cases

@pytest.mark.parametrize("case", CASES, ids=[c.name for c in CASES])
def test_program_case(case, tmp_path):
    if case.missing_tools():
        pytest.skip(f"needs {', '.join(case.missing_tools())}")
    problems = caselib.evaluate(case, str(tmp_path))
    assert not problems, "\n".join(problems)


# ---------------------------------------------------------------- mutations

def _mutated(m, tmp_path) -> str:
    case = CASE_BY_NAME[m.case]
    project = caselib.materialize(case, str(tmp_path))
    if m.file is not None:
        path = os.path.join(project, *m.file.split("/"))
    else:
        path = caselib.module_file(project)
    with open(path, encoding="utf-8", newline="") as fh:
        text = fh.read()
    edited: set[int] = set()
    for old, new in m.edits():
        assert text.count(old) == 1, f"{m.id}: expected exactly one {old[:60]!r}, found {text.count(old)}"
        at = text.index(old)
        text = text[:at] + new + text[at + len(old):]
        first = text[:at].count("\n") + 1
        edited |= set(range(first - 1, first + new.count("\n") + 2))
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)
    return project, path, edited


@pytest.mark.parametrize("m", MUTATIONS, ids=[m.id for m in MUTATIONS])
def test_mutation(m, tmp_path):
    project, path, edited = _mutated(m, tmp_path)
    diags = caselib.check_path(project).diagnostics
    shown = "\n".join(d.format() for d in diags)
    assert sorted({d.code for d in diags}) == sorted(set(m.codes)), shown
    # the rule under test fired itself: on an edited line, or with its own message
    rule = m.codes[0]
    if m.primary is not None:
        assert any(d.code == rule and m.primary in d.message for d in diags), shown
    else:
        here = os.path.normcase(path)
        assert any(d.code == rule and os.path.normcase(d.file) == here and d.line in edited for d in diags), shown


def test_mutation_ids_are_unique_and_cases_exist():
    ids = [m.id for m in MUTATIONS]
    assert len(ids) == len(set(ids))
    missing = sorted({m.case for m in MUTATIONS} - set(CASE_BY_NAME))
    assert not missing, missing
    assert all(m.codes and all(c in CODES for c in m.codes) for m in MUTATIONS)


def test_every_rule_code_has_a_negative_case():
    """Every checker rule is proven to fire by at least one mutation or negative program case."""
    seen = {c for m in MUTATIONS for c in m.codes}
    seen |= {code for c in CASES if c.mode == "check" for code in c.detail.split() if code in CODES}
    # R605 needs git history and R901 a program the backend cannot compile; tests/test_refined.py covers both
    untested = sorted(set(CODES) - seen - {"R605", "R901"})
    assert not untested, f"rule codes with no negative case: {untested}"


def test_every_operation_compiles(tmp_path):
    """Not only what `main` reaches: every operation and test in every program and worked example compiles."""
    from refined.codegen import compile_roots
    projects = [caselib.materialize(c, str(tmp_path / str(i))) for i, c in enumerate(CASES)
                if not (c.mode == "check" and c.detail != "ok")]
    examples = os.path.join(caselib.ROOT, "docs", "refined-examples")
    projects += [os.path.join(examples, d) for d in sorted(os.listdir(examples))]
    for project in projects:
        res = caselib.check_path(project)
        assert res.ok, project
        roots = [(m.short, op) for m in res.world.modules.values() for op, info in m.op_infos.items()
                 if not info.tparams]
        _module, diags = compile_roots(res.world, roots)
        assert not diags, [d.format() for d in diags]


def test_every_program_case_runs():
    """Every positive and edge program compiles and runs (or traps, or runs its tests); none is merely checked."""
    idle = [c.name for c in CASES if c.kind in ("positive", "edge") and c.mode not in ("run", "trap", "test")]
    assert not idle, f"cases that do not run: {idle}"


# ---------------------------------------------------------------- source locations

@pytest.mark.parametrize("m", MUTATIONS[::4], ids=[m.id for m in MUTATIONS[::4]])
def test_diagnostics_point_at_real_lines(m, tmp_path):
    project, _path, _edited = _mutated(m, tmp_path)
    for d in caselib.check_path(project).diagnostics:
        assert os.path.exists(d.file), d.format()
        with open(d.file, encoding="utf-8", errors="replace") as fh:
            count = len(fh.read().split("\n"))
        assert 1 <= d.line <= count, d.format()


def test_a_single_edit_is_reported_on_its_own_line(tmp_path):
    case = CASE_BY_NAME["22-edge/minimal"]
    project = caselib.materialize(case, str(tmp_path))
    path = caselib.module_file(project)
    lines = open(path, encoding="utf-8").read().split("\n")
    target = next(i for i, line in enumerate(lines) if line == "main async false")
    lines[target] = "main async maybe"
    open(path, "w", encoding="utf-8", newline="\n").write("\n".join(lines))
    shape = [d for d in caselib.check_path(project).diagnostics if d.code == "R205"]
    assert [d.line for d in shape] == [target + 1]


# ---------------------------------------------------------------- determinism

def test_check_output_is_deterministic(tmp_path):
    m = next(m for m in MUTATIONS if m.id == "module-cycle")
    project, _path, _edited = _mutated(m, tmp_path)
    first = caselib.refined("check", project, "--json", "--no-cache").stdout
    second = caselib.refined("check", project, "--json", "--no-cache").stdout
    assert first == second and json.loads(first)["errorCount"] > 0


def test_emitted_ir_is_deterministic(tmp_path):
    project = caselib.materialize(CASE_BY_NAME["06-recursion/recursion"], str(tmp_path))
    first = caselib.refined("emit-ir", project)
    second = caselib.refined("emit-ir", project)
    assert first.returncode == 0, first.stdout + first.stderr
    assert first.stdout == second.stdout and "define" in first.stdout


def test_run_is_deterministic(tmp_path):
    project = caselib.materialize(CASE_BY_NAME["08-strings-collections/sorting"], str(tmp_path))
    first, second = caselib.refined("run", project), caselib.refined("run", project)
    assert first.returncode == second.returncode == 0
    assert first.stdout == second.stdout and first.stdout


# ---------------------------------------------------------------- tooling (section 23)

def test_cli_check_json_shape():
    proc = caselib.refined("check", os.path.join(caselib.ROOT, "docs", "refined-examples", "hello"), "--json")
    payload = json.loads(proc.stdout)
    assert proc.returncode == 0
    assert payload == {"surface": "refined.check.v1", "ok": True, "errorCount": 0, "diagnostics": [],
                       "cached": payload["cached"]}


def test_cli_run_refuses_a_library(tmp_path):
    project = caselib.materialize(CASE_BY_NAME["20-testing/tests-pass"], str(tmp_path))
    proc = caselib.refined("run", project)
    assert proc.returncode == 1 and "R601" in proc.stdout


def test_cli_run_refuses_a_module_file_without_project():
    case = CASE_BY_NAME["22-edge/minimal"]
    proc = caselib.refined("run", case.path)
    assert proc.returncode == 1 and "R601" in proc.stdout


def test_cli_rejects_unknown_command():
    proc = caselib.refined("format", ".")
    assert proc.returncode == 2


def test_check_reports_unreadable_source_encoding(tmp_path):
    case = CASE_BY_NAME["22-edge/minimal"]
    project = caselib.materialize(case, str(tmp_path))
    path = caselib.module_file(project)
    with open(path, "ab") as fh:
        fh.write(b"\n# \xff\xfe not UTF-8\n")
    # the unreadable module is reported, and so is the entry that now names nothing
    assert sorted(caselib.codes(project)) == ["R102", "R601"]


# ---------------------------------------------------------------- stress

def _project(tmp_path, name: str, module_text: str, extra: dict[str, str] | None = None, entry=True) -> str:
    d = tmp_path / name
    d.mkdir()
    mods = [name] + sorted(extra or {})
    rows = [f"{name}Project is project", f'{name}Project purpose "A generated stress program"',
            f"{name}Project target {'console' if entry else 'library'}", f'{name}Project version "0.1.0"',
            f"{name}Project language refined 1", f"{name}Project standardLibrary 1",
            *allows_rows(f"{name}Project", [module_text, *(extra or {}).values()]), f"{name}Project requires none"]
    rows += [f"{name}Project includesModule {m}" for m in mods]
    rows.append(f"{name}Project entry {name + '.main' if entry else 'none'}")
    (d / "build.sem").write_text("\n".join(rows) + "\n", encoding="utf-8")
    caselib.approve(str(d))
    with open(d / f"{name}.sem", "w", encoding="utf-8", newline="\n") as fh:
        fh.write(module_text)
    for m, text in (extra or {}).items():
        with open(d / f"{m}.sem", "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
    return str(d)


def _run(project: str) -> tuple[int, list[str]]:
    diags = caselib.diagnostics(project)
    assert not diags, "\n".join(diags[:20])
    proc = caselib.refined("run", project, timeout=600)
    return proc.returncode, proc.stdout.splitlines()


def test_stress_thousands_of_values(tmp_path):
    """22 Thousands of variables, 22 Large source files: 2,000 lets and 2,000 calls in one operation."""
    n = 2000
    p = sb.Prog("manyValues", "Add one, two thousand times, through two thousand named results",
                imports=["standard.console", "standard.math"])
    p.add(sb.STDOUT_CAP).add(sb.show_int())
    steps = [("begin", f"do add{i}") for i in range(n)] + [("begin", "do showTotal"), ("begin", "return ok okCode")]
    lets = ["one Int64 1 immutable", "start Int64 0 immutable"]
    p.add(sb.main_op(steps, lets=lets))
    prev = "start"
    for i in range(n):
        p.add(sb.call(f"add{i}", "main", "math.addInt64", (f"left Int64 {prev} copy", "right Int64 one copy"),
                      out=f"total{i} Int64"))
        prev = f"total{i}"
    p.add(sb.printer("main", "showTotal", "Int64", prev))
    code, out = _run(_project(tmp_path, "manyValues", p.render()))
    assert (code, out) == (0, [str(n)])


def test_stress_thousands_of_operations(tmp_path):
    """22 Thousands of operations, 5 Function invocation: a chain of 1,000 operations, each calling the next."""
    n = 1000
    p = sb.Prog("manyOps", "Count the length of a chain of operations", imports=["standard.console", "standard.math"])
    p.add(sb.STDOUT_CAP).add(sb.show_int())
    for i in range(n):
        if i == n - 1:
            p.add(sb.op(f"link{i}", "Return one", [("begin", "return ok one")], output="Int64",
                        lets=("one Int64 1 immutable",)))
            continue
        p.add(sb.op(f"link{i}", "Return one more than the rest of the chain",
                    [("begin", "do next"), ("begin", "do addOne"), ("begin", "return ok total")], output="Int64",
                    lets=("one Int64 1 immutable",)) + "\n\n" +
              sb.call("next", f"link{i}", f"link{i + 1}", (), out="rest Int64") + "\n\n" +
              sb.call("addOne", f"link{i}", "math.addInt64", ("left Int64 rest copy", "right Int64 one copy"),
                      out="total Int64"))
    p.add(sb.main_op([("begin", "do chain"), ("begin", "do showLength"), ("begin", "return ok okCode")]))
    p.add(sb.call("chain", "main", "link0", (), out="length Int64"))
    p.add(sb.printer("main", "showLength", "Int64", "length"))
    code, out = _run(_project(tmp_path, "manyOps", p.render()))
    assert (code, out) == (0, [str(n)])


def test_stress_deeply_nested_control_flow(tmp_path):
    """22 Deeply nested control flow, 4 Nested conditionals: 300 nested decisions, each leaving early if false."""
    n = 300
    p = sb.Prog("deepBranches", "Pass through 300 nested decisions", imports=["standard.console"])
    p.add(sb.STDOUT_CAP).add(sb.show_int())
    steps = [("begin", "goto level0")]
    for i in range(n):
        steps.append((f"level{i}", f"branch if yes goto level{i + 1} else goto out"))
    steps += [(f"level{n}", "do showDepth"), (f"level{n}", "return ok okCode"), ("out", "return ok failCode")]
    p.add(sb.main_op(steps, lets=("yes Bool true immutable", f"depth Int64 {n} immutable",
                                  "failCode ExitCode 1 immutable")))
    p.add(sb.printer("main", "showDepth", "Int64", "depth"))
    code, out = _run(_project(tmp_path, "deepBranches", p.render()))
    assert (code, out) == (0, [str(n)])


def test_stress_extremely_long_string(tmp_path):
    """22 Extremely long strings: a 200,000-byte literal keeps every byte."""
    n = 200_000
    p = sb.Prog("longString", "Measure a very long string literal", imports=["standard.console", "standard.string"])
    p.add(sb.STDOUT_CAP).add(sb.show_int())
    p.add(sb.main_op([("begin", "do measure"), ("begin", "do showLength"), ("begin", "return ok okCode")],
                     lets=(f'long String "{"ab" * (n // 2)}" immutable',)))
    p.add(sb.call("measure", "main", "string.byteLength", ("text String long lend",), out="length Int64"))
    p.add(sb.printer("main", "showLength", "Int64", "length"))
    code, out = _run(_project(tmp_path, "longString", p.render()))
    assert (code, out) == (0, [str(n)])


def _recursion_program(depth: int, limit: int) -> str:
    p = sb.Prog("deepRecursion", "Recurse to a given depth and report it",
                imports=["standard.console", "standard.math", "standard.compare"])
    p.add(sb.STDOUT_CAP).add(sb.show_int())
    p.add(sb.op("descend", "Return n by recursing n times",
                [("begin", "do atZero"), ("begin", "branch if zeroReached goto done else goto step"),
                 ("done", "return ok zero"), ("step", "do less"), ("step", "do recurse"), ("step", "do addOne"),
                 ("step", "return ok counted")],
                inputs=("n Int64 copied",), output="Int64", recursion=str(limit),
                lets=("zero Int64 0 immutable", "one Int64 1 immutable")) + "\n\n" + "\n\n".join([
        sb.call("atZero", "descend", "compare.equalInt64", ("left Int64 n copy", "right Int64 zero copy"),
                out="zeroReached Bool"),
        sb.call("less", "descend", "math.subtractInt64", ("left Int64 n copy", "right Int64 one copy"),
                out="smaller Int64"),
        sb.call("recurse", "descend", "descend", ("n Int64 smaller copy",), out="inner Int64"),
        sb.call("addOne", "descend", "math.addInt64", ("left Int64 inner copy", "right Int64 one copy"),
                out="counted Int64")]))
    p.add(sb.main_op([("begin", "do goDeep"), ("begin", "do showDepth"), ("begin", "return ok okCode")],
                     lets=(f"depth Int64 {depth} immutable",)))
    p.add(sb.call("goDeep", "main", "descend", ("n Int64 depth copy",), out="reached Int64"))
    p.add(sb.printer("main", "showDepth", "Int64", "reached"))
    return p.render()


def test_stress_deep_recursion(tmp_path):
    """22 Deep recursion, 16 Function call stack: 200,000 nested calls within the stated bound."""
    code, out = _run(_project(tmp_path, "deepRecursion", _recursion_program(200_000, 200_001)))
    assert (code, out) == (0, ["200000"])


def test_stress_stack_exhaustion_traps(tmp_path):
    """6 Stack overflow detection, 17 Stack overflow protection: a recursion whose stated bound is larger than
    the stack can hold traps with a message when the stack runs low; it never crashes the process."""
    project = _project(tmp_path, "deepRecursion", _recursion_program(20_000_000, 20_000_001))
    assert not caselib.diagnostics(project)
    proc = caselib.refined("run", project, timeout=600)
    assert proc.returncode == caselib.TRAP_EXIT_CODE, (proc.returncode, proc.stderr[-500:])
    assert "ran out of stack before reaching maxRecursion 20000001" in proc.stderr


def test_stress_very_large_collection(tmp_path):
    """22 Very large collections, 22 Repeated allocation/deallocation: a list grown to 500,000 items."""
    n = 500_000
    p = sb.Prog("bigList", "Grow a list to half a million items",
                imports=["standard.console", "standard.math", "standard.compare", "standard.list"])
    p.add(sb.STDOUT_CAP).add(sb.show_int())
    p.add('Numbers is typeInstance\nNumbers purpose "A growable list of whole numbers"\nNumbers in none\n'
          'Numbers instantiates list.List Int64')
    p.add(sb.main_op([("begin", "do makeNumbers"), ("begin", "goto fill"),
                      ("fill", "do filled"), ("fill", "branch if isFilled goto report else goto appendStep"),
                      ("appendStep", "do appendIndex"), ("appendStep", "do advance"),
                      ("appendStep", "set index nextIndex"), ("appendStep", "goto fill"),
                      ("report", "do countNumbers"), ("report", "do showCount"), ("report", "return ok okCode")],
                     lets=("one Int64 1 immutable", f"limit Int64 {n} immutable", "index Int64 0 mutable"),
                     loops={"fill": {"kind": "counted", "facts": [f"maxIterations {n}", "counter index"]},
                            "appendStep": {"within": "fill"}}, heap=True))
    p.add(f"store is region\nstore in main\nstore strategy arena\nstore maxBytes {64 * n}\nstore released atReturn")
    p.add(sb.call("makeNumbers", "main", "Numbers.new", ("region Region store lend",), out="numbers Numbers",
                  owned="store"))
    p.add(sb.call("filled", "main", "compare.greaterOrEqualInt64", ("left Int64 index copy", "right Int64 limit copy"),
                  out="isFilled Bool"))
    p.add(sb.call("appendIndex", "main", "Numbers.append", ("list Numbers numbers lendMutable", "item Int64 index copy")))
    p.add(sb.call("advance", "main", "math.addInt64", ("left Int64 index copy", "right Int64 one copy"),
                  out="nextIndex Int64"))
    p.add(sb.call("countNumbers", "main", "Numbers.length", ("list Numbers numbers lend",), out="count Int64"))
    p.add(sb.printer("main", "showCount", "Int64", "count"))
    code, out = _run(_project(tmp_path, "bigList", p.render()))
    assert (code, out) == (0, [str(n)])


def test_stress_large_dependency_graph(tmp_path):
    """22 Large dependency graphs, 9 Dependency management: 40 modules in a chain, each calling the one below."""
    n = 40
    extra = {}
    for i in range(n):
        imports = ["standard.math", "standard.test"] + ([f"layer{i + 1}"] if i < n - 1 else [])
        p = sb.Prog(f"layer{i}", f"Layer {i} of a module chain", imports=imports, exports=["depth"])
        if i == n - 1:
            body = sb.op("depth", "Return one", [("begin", "return ok one")], output="Int64",
                         invariant=[("countsLayers", "Returns the number of layers from here down")],
                         lets=("one Int64 1 immutable",))
        else:
            body = sb.op("depth", "Return one more than the layer below",
                         [("begin", "do below"), ("begin", "do addOne"), ("begin", "return ok total")],
                         output="Int64", invariant=[("countsLayers", "Returns the number of layers from here down")],
                         lets=("one Int64 1 immutable",)) + "\n\n" + \
                sb.call("below", "depth", f"layer{i + 1}.depth", (), out="rest Int64") + "\n\n" + \
                sb.call("addOne", "depth", "math.addInt64", ("left Int64 rest copy", "right Int64 one copy"),
                        out="total Int64")
        p.add(body)
        if i == n - 1:
            p.imports.remove("standard.math")
        extra[f"layer{i}"] = p.render()
        expected = n - i
        test = sb.op("depthTest", f"Layer {i} reports {expected} layers",
                     [("begin", "do run"), ("begin", "do expect"), ("begin", "return ok none")], kind="test",
                     verifies=("depth countsLayers",), lets=(f"expected Int64 {expected} immutable",)) + "\n\n" + \
            sb.call("run", "depthTest", "depth", (), out="actual Int64") + "\n\n" + \
            sb.call("expect", "depthTest", "test.assertEqualInt64", ("expected Int64 expected copy",
                                                                       "actual Int64 actual copy"))
        extra[f"layer{i}.test"] = test + "\n"
    app = sb.Prog("graph", "Print the depth of the module chain", imports=["standard.console", "layer0"])
    app.add(sb.STDOUT_CAP).add(sb.show_int())
    app.add(sb.main_op([("begin", "do measure"), ("begin", "do showDepth"), ("begin", "return ok okCode")]))
    app.add(sb.call("measure", "main", "layer0.depth", (), out="layers Int64"))
    app.add(sb.printer("main", "showDepth", "Int64", "layers"))
    modules = {k: v for k, v in extra.items() if not k.endswith(".test")}
    project = _project(tmp_path, "graph", app.render(), modules)
    for k, v in extra.items():
        if k.endswith(".test"):
            with open(os.path.join(project, f"{k}.sem"), "w", encoding="utf-8", newline="\n") as fh:
                fh.write(v)
    code, out = _run(project)
    assert (code, out) == (0, [str(n)])


# ---------------------------------------------------------------- fuzz

_FUZZ_TOKENS = ["none", "true", "unset", "begin", "Int64", "String", "x", "Zz", "0", "-1", "99999999999999999999",
                '"text"', '"', "#", "\t", "\x00", "é", " ", "is", "operation", "at", "goto", "...", "a.b.c"]


def _fuzz_once(text: str, rnd: random.Random) -> str:
    lines = text.split("\n")
    for _ in range(rnd.randint(1, 4)):
        if not lines:
            break
        i = rnd.randrange(len(lines))
        action = rnd.randrange(6)
        if action == 0:
            del lines[i]
        elif action == 1:
            lines.insert(i, lines[i])
        elif action == 2:
            j = rnd.randrange(len(lines))
            lines[i], lines[j] = lines[j], lines[i]
        elif action == 3:
            words = lines[i].split(" ")
            words[rnd.randrange(len(words))] = rnd.choice(_FUZZ_TOKENS)
            lines[i] = " ".join(words)
        elif action == 4:
            lines[i] = lines[i][:rnd.randrange(len(lines[i]) + 1)]
        else:
            lines.insert(i, " ".join(rnd.choice(_FUZZ_TOKENS) for _ in range(rnd.randint(1, 5))))
    return "\n".join(lines)


FUZZ_CASES = [c for c in CASES if os.path.isfile(c.path)]


@pytest.mark.parametrize("case", FUZZ_CASES, ids=[c.name for c in FUZZ_CASES])
def test_fuzz_checker_never_crashes(case, tmp_path):
    """20 Fuzz testing, 22 Malformed input, 22 Randomized program generation: random damage to every
    single-file case yields diagnostics (with known codes and real lines), never an exception."""
    rnd = random.Random(f"fuzz:{case.name}")
    original = open(case.path, encoding="utf-8").read()
    for attempt in range(12):
        d = tmp_path / f"try{attempt}"
        d.mkdir()
        project = caselib.materialize(case, str(d))
        path = caselib.module_file(project)
        damaged = _fuzz_once(original, rnd)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(damaged)
        try:
            diags = caselib.check_path(project).diagnostics
        except Exception as exc:  # pragma: no cover - the failure itself is the report
            pytest.fail(f"checker crashed on attempt {attempt}: {exc!r}\n--- source ---\n{damaged}")
        count = len(damaged.split("\n"))
        for dg in diags:
            assert dg.code in CODES, dg.format()
            if os.path.normcase(dg.file) == os.path.normcase(path):
                assert 1 <= dg.line <= count, dg.format()


# ---------------------------------------------------------------- differential

def _wrap(v: int) -> int:
    return (v + (1 << 63)) % (1 << 64) - (1 << 63)


def _model(op: str, x: int, y: int):
    """Python model of the Int64 library targets: ('ok', value) or ('trap', message part)."""
    def checked(v):
        return ("ok", v) if INT64_MIN <= v <= INT64_MAX else ("trap", "overflowed `Int64`")
    if op == "addInt64":
        return checked(x + y)
    if op == "subtractInt64":
        return checked(x - y)
    if op == "multiplyInt64":
        return checked(x * y)
    if op in ("divideInt64", "remainderInt64"):
        if y == 0:
            return ("trap", "divided by zero")
        if x == INT64_MIN and y == -1:
            return ("trap", "overflowed `Int64`")
        q = abs(x) // abs(y) * (1 if (x >= 0) == (y >= 0) else -1)
        return ("ok", q) if op == "divideInt64" else ("ok", x - q * y)
    if op == "wrappingAddInt64":
        return ("ok", _wrap(x + y))
    if op == "wrappingSubtractInt64":
        return ("ok", _wrap(x - y))
    if op == "wrappingMultiplyInt64":
        return ("ok", _wrap(x * y))
    if op.startswith("saturating"):
        exact = {"saturatingAddInt64": x + y, "saturatingSubtractInt64": x - y, "saturatingMultiplyInt64": x * y}[op]
        return ("ok", max(INT64_MIN, min(INT64_MAX, exact)))
    if op == "andInt64":
        return ("ok", x & y)
    if op == "orInt64":
        return ("ok", x | y)
    if op == "xorInt64":
        return ("ok", x ^ y)
    if op in ("shiftLeftInt64", "shiftRightInt64"):
        if not 0 <= y <= 63:
            return ("trap", "shift amount outside")
        return ("ok", _wrap(x << y) if op == "shiftLeftInt64" else x >> y)
    if op == "powerInt64":
        if y < 0:
            return ("trap", "negative exponent")
        if abs(x) > 1 and y > 64:
            return ("trap", "overflowed `Int64`")
        return checked(x ** y) if abs(x) > 1 else ("ok", x ** (y % 2) if x == -1 else (x if y else 1))
    raise AssertionError(op)


_DIFF_OPS = {
    "math": ["addInt64", "subtractInt64", "multiplyInt64", "divideInt64", "remainderInt64", "wrappingAddInt64",
             "wrappingSubtractInt64", "wrappingMultiplyInt64", "saturatingAddInt64", "saturatingSubtractInt64",
             "saturatingMultiplyInt64", "powerInt64"],
    "bits": ["andInt64", "orInt64", "xorInt64", "shiftLeftInt64", "shiftRightInt64"],
}
_MODULE_OF = {name: mod for mod, names in _DIFF_OPS.items() for name in names}


def _operand(rnd: random.Random, op: str, slot: int) -> int:
    if op.startswith("shift") and slot == 1:
        return rnd.choice([0, 1, 7, 31, 62, 63, rnd.randrange(0, 64)])
    if op == "powerInt64" and slot == 1:
        return rnd.choice([0, 1, 2, 3, rnd.randrange(0, 70), 10 ** 18])
    if op == "powerInt64":
        return rnd.choice([-3, -2, -1, 0, 1, 2, 3, 10, rnd.randrange(-50, 50)])
    return rnd.choice([0, 1, -1, 2, -2, 7, -7, INT64_MAX, INT64_MIN, INT64_MAX - 1, INT64_MIN + 1,
                       rnd.randrange(-1000, 1000), rnd.randrange(INT64_MIN, INT64_MAX),
                       rnd.randrange(-(1 << 31), 1 << 31)])


def _slots(op: str) -> tuple[str, str]:
    if op.startswith("shift"):
        return ("value", "amount")
    if op == "powerInt64":
        return ("base", "exponent")
    return ("left", "right")


def _diff_program(name: str, items: list[tuple[str, int, int]]) -> str:
    imports = sorted({f"standard.{_MODULE_OF[op]}" for op, _x, _y in items} | {"standard.console"})
    p = sb.Prog(name, "Compute random library arithmetic and print each result", imports=imports)
    p.add(sb.STDOUT_CAP).add(sb.show_int())
    steps, lets = [], []
    for i, (op, x, y) in enumerate(items):
        lets += [f"x{i} Int64 {x} immutable", f"y{i} Int64 {y} immutable"]
        steps += [("begin", f"do compute{i}"), ("begin", f"do show{i}")]
    steps.append(("begin", "return ok okCode"))
    p.add(sb.main_op(steps, lets=lets))
    for i, (op, _x, _y) in enumerate(items):
        a, b = _slots(op)
        p.add(sb.call(f"compute{i}", "main", f"{_MODULE_OF[op]}.{op}", (f"{a} Int64 x{i} copy", f"{b} Int64 y{i} copy"),
                      out=f"result{i} Int64"))
        p.add(sb.printer("main", f"show{i}", "Int64", f"result{i}"))
    return p.render()


@pytest.mark.parametrize("seed", range(3))
def test_differential_integer_arithmetic(seed, tmp_path):
    """20 Differential testing, 20 Property-based tests, 3 Integer overflow: random library arithmetic agrees
    with a Python model; every input the model says traps does trap, with the right message."""
    rnd = random.Random(f"diff:{seed}")
    ops = [op for names in _DIFF_OPS.values() for op in names]
    ok_items, trap_items = [], []
    while len(ok_items) < 60:
        op = rnd.choice(ops)
        x, y = _operand(rnd, op, 0), _operand(rnd, op, 1)
        kind, value = _model(op, x, y)
        (ok_items if kind == "ok" else trap_items).append((op, x, y, value))
    code, out = _run(_project(tmp_path, f"diff{seed}", _diff_program(f"diff{seed}", [i[:3] for i in ok_items])))
    assert code == 0
    assert out == [str(v) for *_rest, v in ok_items]
    for k, (op, x, y, message) in enumerate(trap_items[:3]):
        project = _project(tmp_path, f"trap{seed}x{k}", _diff_program(f"trap{seed}x{k}", [(op, x, y)]))
        proc = caselib.refined("run", project)
        assert proc.returncode == caselib.TRAP_EXIT_CODE and message in proc.stderr, (op, x, y, proc.stderr)


# ---------------------------------------------------------------- coverage map

def test_coverage_map_is_current():
    """docs/test-suite.md is generated from the checklist, the cases, and the notes; it must be current."""
    expected = coverage_map.render(CASES, MUTATIONS)
    with open(coverage_map.DOC, encoding="utf-8") as fh:
        actual = fh.read()
    assert actual == expected, "docs/test-suite.md is out of date: run `python tests/suite/coverage_map.py --write`"


def test_every_checklist_item_has_evidence_or_a_reason():
    problems = coverage_map.problems(CASES, MUTATIONS)
    assert not problems, "\n".join(problems)


def test_generated_evidence_names_real_tests():
    import test_runtime_nolibc
    import test_tooling
    missing = sorted(name for name in coverage_map.GENERATED
                     if not callable(globals().get(name)) and not any(callable(getattr(module, name, None))
                                                                      for module in (test_tooling, test_runtime_nolibc)))
    assert not missing, missing

