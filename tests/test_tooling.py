"""Tests for the tools around the language: formatter, REPL, language server, build cache, benchmarks,
instrumented runs (trace, coverage, profile, debugger), cross-compilation, WebAssembly, and signals."""
from __future__ import annotations

import json
import os
import random
import shutil
import subprocess
import sys
import urllib.request

import pytest

SUITE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "suite")
sys.path.insert(0, SUITE)

import caselib  # noqa: E402
import sembuild as sb  # noqa: E402

CASES = caselib.discover()
CASE = {c.name: c for c in CASES}
EXAMPLES = os.path.join(caselib.ROOT, "docs", "refined-examples")


# ---------------------------------------------------------------- formatter

def test_formatter_repository_is_canonical():
    """23 Formatter: every source in the repository is already in the formatter's layout."""
    proc = caselib.refined("fmt", "--check", EXAMPLES, caselib.PROGRAMS)
    assert proc.returncode == 0, proc.stdout


def test_formatter_layout_keeps_comments():
    from refined.fmt import format_text
    messy = ('# header   comment kept as written\n\n\n\nmain is operation\nmain purpose   "Keep  this"\t# trailing\n'
             "x is record   \n\n\n")
    tidy = format_text(messy)
    assert tidy == ('# header   comment kept as written\n\nmain is operation\nmain purpose "Keep  this" # trailing\n\n'
                    "x is record\n")
    assert format_text(tidy) == tidy
    assert format_text('main purpose "unterminated\n') is None


def test_formatter_undoes_added_spacing():
    """Spaces and blank lines added anywhere come back out exactly."""
    from refined.fmt import format_text
    rnd = random.Random("fmt")
    for case in [c for c in CASES if os.path.isfile(c.path)][:25]:
        original = open(case.path, encoding="utf-8").read()
        lines = []
        for line in original.split("\n"):
            if line and not line.startswith("#") and '"' not in line:
                line = line.replace(" ", " " * rnd.randint(1, 3)) + " " * rnd.randint(0, 2)
            lines.append(line)
            if line == "" and rnd.random() < 0.5:
                lines.append("")  # a run of blank lines collapses back to one
        assert format_text("\n".join(lines)) == original, case.name


# ---------------------------------------------------------------- REPL

REPL_SESSION = """stdoutWriter is capability
stdoutWriter purpose "Authority to write lines to standard output"
stdoutWriter grants write console.stdout
stdoutWriter scope none
main is operation
main purpose "Print a greeting from the REPL"
main invariant none
main typeParam none
main input none
main output ExitCode
main outputOwner none
main raises none
main effect write console.stdout
main uses stdoutWriter
main memory heap false
main async false
main maxRecursion none
main label begin loopKind none
main label begin within none
main label done loopKind none
main label done within none
main let greeting immutable String "Hello from the REPL"
main let okCode immutable ExitCode 0
main at begin do printIt
main at begin branch ifError printIt goto done else goto done
main at done return ok okCode
main nonsense row
:check
:undo
printIt is call
printIt rationale "A REPL demo has nowhere to report a failed write"
printIt in main
printIt invokes console.writeLine
printIt arg text String greeting lend
printIt out none
printIt ownedBy none
printIt cleanedBy none
printIt borrows none
printIt catch printError console.WriteError
:check
:run
:quit
"""


def test_repl_checks_and_runs():
    """23 REPL behavior: typed rows are checked, a mistake is reported and undone, and the program runs."""
    proc = subprocess.run([sys.executable, caselib.COMPILER, "repl"], input=REPL_SESSION, capture_output=True,
                          text=True, encoding="utf-8", timeout=300)
    out = proc.stdout
    assert proc.returncode == 0, out + proc.stderr
    assert "removed: main nonsense row" in out
    assert "\nok\n" in out and "Hello from the REPL" in out and "exit 0" in out


# ---------------------------------------------------------------- language server

def _lsp_read(proc) -> dict:
    length = None
    while True:
        line = proc.stdout.readline().strip()
        if not line:
            break
        name, _, value = line.decode().partition(":")
        if name.lower() == "content-length":
            length = int(value)
    return json.loads(proc.stdout.read(length))


def _lsp_send(proc, message: dict) -> None:
    body = json.dumps(message).encode()
    proc.stdin.write(f"Content-Length: {len(body)}\r\n\r\n".encode() + body)
    proc.stdin.flush()


def _lsp_wait_diagnostics(proc, uri: str) -> list:
    while True:
        msg = _lsp_read(proc)
        if msg.get("method") == "textDocument/publishDiagnostics" and msg["params"]["uri"] == uri:
            return msg["params"]["diagnostics"]


def test_language_server(tmp_path):
    """23 Language Server Protocol (LSP), 23 IDE integration: diagnostics for unsaved text, hover, formatting."""
    project = caselib.materialize(CASE["22-edge/minimal"], str(tmp_path))
    path = caselib.module_file(project)
    uri = "file:" + urllib.request.pathname2url(os.path.abspath(path))
    good = open(path, encoding="utf-8").read()
    bad = good.replace("main async false", "main async maybe")
    proc = subprocess.Popen([sys.executable, caselib.COMPILER, "lsp"], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    try:
        _lsp_send(proc, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        assert _lsp_read(proc)["result"]["capabilities"]["hoverProvider"]
        _lsp_send(proc, {"jsonrpc": "2.0", "method": "textDocument/didOpen",
                         "params": {"textDocument": {"uri": uri, "languageId": "semanticscript", "version": 1,
                                                     "text": bad}}})
        assert "R205" in {d["code"] for d in _lsp_wait_diagnostics(proc, uri)}
        line = next(i for i, text in enumerate(bad.split("\n")) if text.startswith("main purpose"))
        _lsp_send(proc, {"jsonrpc": "2.0", "id": 2, "method": "textDocument/hover",
                         "params": {"textDocument": {"uri": uri}, "position": {"line": line, "character": 1}}})
        assert "Return exit status 0" in _lsp_read(proc)["result"]["contents"]["value"]
        spaced = good.replace("main input none", "main input  none")
        _lsp_send(proc, {"jsonrpc": "2.0", "method": "textDocument/didChange",
                         "params": {"textDocument": {"uri": uri, "version": 2}, "contentChanges": [{"text": spaced}]}})
        assert _lsp_wait_diagnostics(proc, uri) == []
        _lsp_send(proc, {"jsonrpc": "2.0", "id": 3, "method": "textDocument/formatting",
                         "params": {"textDocument": {"uri": uri}, "options": {}}})
        edits = _lsp_read(proc)["result"]
        assert edits and edits[0]["newText"] == good
        _lsp_send(proc, {"jsonrpc": "2.0", "id": 4, "method": "shutdown"})
        assert _lsp_read(proc)["result"] is None
        _lsp_send(proc, {"jsonrpc": "2.0", "method": "exit"})
        assert proc.wait(timeout=30) == 0
    finally:
        proc.kill()


# ---------------------------------------------------------------- build cache and benchmarks

def test_build_cache_reuses_only_identical_projects(tmp_path):
    """23 Build caching, 23 Incremental builds, 15 Incremental compilation."""
    project = caselib.materialize(CASE["01-variables/variables"], str(tmp_path))
    first = json.loads(caselib.refined("check", project, "--json").stdout)
    second = json.loads(caselib.refined("check", project, "--json").stdout)
    assert (first["cached"], second["cached"]) == (False, True) and first["ok"] and second["ok"]
    with open(caselib.module_file(project), "a", encoding="utf-8") as fh:
        fh.write("\n# an edit\n")
    assert json.loads(caselib.refined("check", project, "--json").stdout)["cached"] is False
    runs = [caselib.refined("run", project) for _ in range(2)]
    assert runs[0].stdout == runs[1].stdout and runs[0].returncode == runs[1].returncode == 0
    assert os.path.isdir(os.path.join(project, ".refined-cache"))


def test_bench_reports_timings(tmp_path):
    """20 Performance benchmarks, 16 Runtime performance."""
    project = caselib.materialize(CASE["08-strings-collections/sorting"], str(tmp_path))
    result = json.loads(caselib.refined("bench", project, "--runs", "3", "--json").stdout)
    assert result["runs"] == 3 and result["exitCode"] == 0
    assert 0 < result["minMs"] <= result["medianMs"] <= result["maxMs"]


# ---------------------------------------------------------------- instrumented runs

def test_trace_coverage_and_profile(tmp_path):
    """20 Execution tracing, 20 Code coverage, 20 CPU profiling, 20 Memory profiling."""
    case = CASE["07-memory/region-list"]
    project = caselib.materialize(case, str(tmp_path))
    proc = caselib.refined("run", project, "--trace", "--coverage", "--profile", "--no-cache")
    assert proc.returncode == 0, proc.stderr
    err = proc.stderr
    assert "trace: memory.main:begin" in err and "trace: memory.main:sumItems" in err
    assert "coverage: " in err and "never ran: memory.main:broken" in err
    assert "profile:" in err and "memory.main (memory.sem:" in err
    assert "memory: region `scratch` of `main` peaked at" in err
    assert proc.stdout.splitlines() == case.stdout


def test_debugger_breakpoints_values_and_stack(tmp_path):
    """20 Debugger integration, 20 Breakpoints, 20 Variable inspection, 20 Stack inspection."""
    project = caselib.materialize(CASE["06-recursion/recursion"], str(tmp_path))
    proc = caselib.refined("run", project, "--debug", "--break", "recursion.factorial:recurse", "--no-cache",
                           stdin="vars\nstack\nstep\nvars\nquit\n")
    err = proc.stderr
    assert "debug: stopped at recursion.factorial:recurse" in err, err
    assert "  n Int64 = 5" in err
    assert "in recursion.factorial (recursion.sem:" in err and "in recursion.main (recursion.sem:" in err
    assert "debug: stopped at recursion.factorial:begin" in err and "  n Int64 = 4" in err
    assert proc.returncode == 1 and "stopped by the user" in err


# ---------------------------------------------------------------- native output

def test_cross_compiles_to_other_targets(tmp_path):
    """23 Cross-compilation, 15 Code generation: object files for other systems from this one."""
    magic = {"x86_64-unknown-linux-gnu": b"\x7fELF", "aarch64-apple-darwin": b"\xcf\xfa\xed\xfe",
             "x86_64-pc-windows-msvc": b"\x64\x86"}
    for triple, head in magic.items():
        out = tmp_path / f"{triple}.o"
        proc = caselib.refined("build", os.path.join(EXAMPLES, "sum"), "--output", str(out), "--target", triple)
        assert proc.returncode == 0, proc.stdout
        assert out.read_bytes().startswith(head), triple
    asm = tmp_path / "sum.s"
    assert caselib.refined("build", os.path.join(EXAMPLES, "sum"), "--output", str(asm),
                           "--kind", "assembly").returncode == 0
    assert "sum.main" in asm.read_text(encoding="utf-8")


@pytest.mark.skipif(shutil.which("node") is None, reason="Node runs the WebAssembly host")
def test_webassembly_runs_under_node(tmp_path):
    """18 WASM integration: worked examples compile to WebAssembly and run in Node with the same output."""
    host = os.path.join(SUITE, "wasm_host.mjs")
    for example, entry, expected in (("hello", "hello.main", "Hello, world!\n"), ("sum", "sum.main", "15\n"),
                                     ("factorial", "mathdemo.main", "120\n")):
        out = tmp_path / f"{example}.wasm"
        built = caselib.refined("build", os.path.join(EXAMPLES, example), "--output", str(out), "--kind", "wasm")
        assert built.returncode == 0, built.stdout
        assert out.read_bytes().startswith(b"\0asm")
        proc = subprocess.run(["node", host, str(out), entry], capture_output=True, text=True, timeout=120)
        assert (proc.returncode, proc.stdout) == (0, expected), proc.stderr


# ---------------------------------------------------------------- signals

@pytest.mark.skipif(os.name == "nt", reason="the interrupt is sent with SIGINT, which POSIX systems deliver")
def test_program_sees_an_interrupt(tmp_path):
    """16 Signal handling: the first interrupt reaches the program, which ends cleanly."""
    import signal
    import time
    p = sb.Prog("interrupts", "Wait for an interrupt and report it",
                imports=["standard.console", "standard.signal", "standard.time"])
    p.add(sb.STDOUT_CAP).add(sb.show_text())
    p.add('interruptReader is capability\ninterruptReader purpose "Authority to observe interrupts"\n'
          "interruptReader grants read signal.interrupts\ninterruptReader scope none")
    p.add(sb.op("main", "Print ready, wait for an interrupt, and say it came",
                [("begin", "do printReady"), ("begin", "do makeDeadline"), ("begin", "start waitIt"),
                 ("begin", "join waitIt"), ("begin", "branch ifError waitIt goto failed else goto got"),
                 ("got", "do printGot"), ("got", "return ok okCode"), ("failed", "return ok failCode")],
                output="ExitCode", effects=("read signal.interrupts", "write console.stdout"),
                uses=("interruptReader", "stdoutWriter"), waits=True,
                lets=('ready immutable String "ready"', 'got immutable String "interrupted"',
                      "tenSeconds immutable Int64 10000", "okCode immutable ExitCode 0",
                      "failCode immutable ExitCode 1")))
    p.add(sb.printer("main", "printReady", "String", "ready"))
    p.add(sb.printer("main", "printGot", "String", "got"))
    p.add(sb.call("makeDeadline", "main", "time.Deadline.after", ("milliseconds Int64 tenSeconds copy",),
                  out="deadline time.Deadline"))
    p.add(sb.call("waitIt", "main", "signal.waitForInterrupt", ("deadline time.Deadline deadline copy",),
                  catch="waitError signal.SignalError", kind="task"))
    d = tmp_path / "interrupts"
    d.mkdir()
    (d / "build.sem").write_text('interruptsProject is project\ninterruptsProject purpose "Wait for an interrupt"\n'
                                 'interruptsProject target console\ninterruptsProject version "0.1.0"\n'
                                 "interruptsProject language refined-1\ninterruptsProject standardLibrary 1\n"
                                 "interruptsProject requires none\ninterruptsProject module interrupts\n"
                                 "interruptsProject entry interrupts.main\n", encoding="utf-8")
    (d / "interrupts.sem").write_text(p.render(), encoding="utf-8")
    assert not caselib.diagnostics(str(d))
    proc = subprocess.Popen([sys.executable, caselib.COMPILER, "run", str(d), "--no-cache"], stdout=subprocess.PIPE,
                            text=True)
    assert proc.stdout.readline().strip() == "ready"
    time.sleep(0.5)
    proc.send_signal(signal.SIGINT)
    out, _ = proc.communicate(timeout=30)
    assert (proc.returncode, out.strip()) == (0, "interrupted")


# ---------------------------------------------------------------- standalone executables

def _has_cc() -> bool:
    from refined.native import find_cc
    return find_cc() is not None


@pytest.mark.skipif(not _has_cc(), reason="linking an executable needs a C compiler")
def test_standalone_executables_match_the_jit(tmp_path):
    """18 Static linking, 16 Program startup: programs link with the C runtime into executables that run with no
    Python and behave exactly as under `refined run` (output, exit code, traps). Programs that call the host
    library trap with that target's name instead."""
    linked = host_only = 0
    for i, case in enumerate(c for c in CASES if c.mode in ("run", "trap") and not c.args and not c.stdin):
        project = caselib.materialize(case, str(tmp_path / str(i)))
        exe = os.path.join(project, "program.exe")
        built = caselib.refined("build", project, "--kind", "executable", "--output", exe)
        assert built.returncode == 0, (case.name, built.stdout)
        proc = subprocess.run([exe], capture_output=True, text=True, cwd=project, timeout=120)
        if "needs the host library" in proc.stderr:
            assert proc.returncode == 70
            host_only += 1
            continue
        if case.mode == "run":
            assert proc.returncode == case.exit_code, (case.name, proc.stderr)
            assert case.stdout is None or proc.stdout.splitlines() == case.stdout, case.name
        else:
            assert proc.returncode == 70 and case.detail in proc.stderr, (case.name, proc.stderr)
        linked += 1
    assert linked >= 30 and host_only >= 1


# ---------------------------------------------------------------- capability scopes at run time

def test_symlink_out_of_scope_traps(tmp_path):
    """13 Capability escalation prevention, 17 Sandboxing: a symbolic link inside the scope that points outside it
    is followed before the scope is checked, so reading through it traps."""
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("not yours", encoding="utf-8")
    d = tmp_path / "linked"
    d.mkdir()
    link_path = "suite-link.txt"
    try:
        os.symlink(outside / "secret.txt", d / "suite-link.txt")
    except (OSError, NotImplementedError):
        if os.name != "nt":
            pytest.skip("this system does not let the test create symbolic links")
        import _winapi  # a directory junction needs no privilege on Windows, and escapes the same way
        _winapi.CreateJunction(str(outside), str(d / "suite-dir"))
        link_path = "suite-dir/secret.txt"
    p = sb.Prog("linked", "Read a file through a link", imports=["standard.fs", "standard.time"])
    p.add('fileAccess is capability\nfileAccess purpose "Authority to read files whose names start with suite-"\n'
          'fileAccess grants read fs.files\nfileAccess scope "suite-"')
    p.add(sb.op("main", "Read suite-link.txt",
                [("begin", "do makeDeadline"), ("begin", "start readIt"), ("begin", "join readIt"),
                 ("begin", "branch ifError readIt goto failed else goto done"),
                 ("done", "return ok okCode"), ("failed", "return ok failCode")],
                output="ExitCode", effects=("read fs.files",), uses=("fileAccess",), heap=True, waits=True,
                lets=(f'path immutable String "{link_path}"', "limit immutable Int64 64",
                      "waitMs immutable Int64 5000", "okCode immutable ExitCode 0", "failCode immutable ExitCode 1")))
    p.add("io is region\nio in main\nio strategy arena\nio capacity 4096\nio released atReturn")
    p.add(sb.call("makeDeadline", "main", "time.Deadline.after", ("milliseconds Int64 waitMs copy",),
                  out="deadline time.Deadline"))
    p.add(sb.call("readIt", "main", "fs.readAll", ("path String path lend", "region Region io lend",
                                                   "maxBytes Int64 limit copy", "deadline time.Deadline deadline copy"),
                  out="content Bytes", owned="io", catch="readError fs.FileError", kind="task"))
    (d / "build.sem").write_text('linkedProject is project\nlinkedProject purpose "Read through a symbolic link"\n'
                                 'linkedProject target console\nlinkedProject version "0.1.0"\n'
                                 "linkedProject language refined-1\nlinkedProject standardLibrary 1\n"
                                 "linkedProject requires none\nlinkedProject module linked\n"
                                 "linkedProject entry linked.main\n", encoding="utf-8")
    (d / "linked.sem").write_text(p.render(), encoding="utf-8")
    assert not caselib.diagnostics(str(d))
    proc = caselib.refined("run", str(d), "--no-cache", cwd=str(d))
    assert proc.returncode == 70 and "which no capability this operation uses allows" in proc.stderr, proc.stderr
