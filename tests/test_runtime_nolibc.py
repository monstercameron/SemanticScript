"""The runtime in SemanticScript, stages 1 and 2 (docs/runtime-in-semanticscript.md, D-120 to D-130).

`refined build --kind executable --runtime semanticscript` links a program with the runtime project in
semanticscript/runtime and no C library. These tests hold it to the bar's first parts: what links behaves exactly
as `refined run` does (output, exit code, trap report), the executable imports from KERNEL32.dll alone, a program
that needs what the runtime does not provide yet is refused before linking, the runtime project checks and passes
its own tests, and the primitive layer (`machine`, `system`, `abi c`) is held to its rules by the checker. Stage 2
adds floating-point text (checked against Python, which `refined run` uses, over a large table of values) and the
host library's buffers, maps, sets, string.fromBytes, and log lines (checked against `refined run`)."""
from __future__ import annotations

import os
import shutil
import struct
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import pytest

SUITE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "suite")
sys.path.insert(0, SUITE)

import caselib  # noqa: E402
from caselib import allows_rows  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import floattable  # noqa: E402
import hosttour  # noqa: E402

RUNTIME = os.path.join(caselib.ROOT, "semanticscript", "runtime")
EXAMPLES = os.path.join(caselib.ROOT, "docs", "refined-examples")
CASES = {c.name: c for c in caselib.discover()}


def _can_link() -> bool:
    from refined.native import find_cc
    cc = find_cc()
    if os.name != "nt" or cc is None:
        return False
    machine = subprocess.run(cc + ["-dumpmachine"], capture_output=True, text=True).stdout
    return "mingw" in machine or "windows" in machine


needs_windows_cc = pytest.mark.skipif(not _can_link(), reason="the runtime in SemanticScript links on Windows, "
                                      "with a MinGW C compiler as the linker")


def _build(project: str, exe: str) -> subprocess.CompletedProcess:
    return caselib.refined("build", project, "--kind", "executable", "--runtime", "semanticscript", "--output", exe)


def _jit(project: str, args=(), stdin: str = "") -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, caselib.COMPILER, "run", project, "--no-cache",
                           *(["--", *args] if args else [])], capture_output=True, text=True, encoding="utf-8",
                          errors="replace", cwd=project, input=stdin, timeout=300)


def _exe(exe: str, project: str, args=(), stdin: str = "") -> subprocess.CompletedProcess:
    return subprocess.run([exe, *args], capture_output=True, text=True, encoding="utf-8", errors="replace",
                          cwd=project, input=stdin, timeout=120)


def imported_dlls(path: str) -> list[str]:
    """The DLLs a PE executable's import directory names, read from the file itself."""
    with open(path, "rb") as fh:
        data = fh.read()
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    assert data[pe:pe + 4] == b"PE\0\0"
    sections, optional_size = struct.unpack_from("<H", data, pe + 6)[0], struct.unpack_from("<H", data, pe + 20)[0]
    optional = pe + 24
    assert struct.unpack_from("<H", data, optional)[0] == 0x20B  # PE32+
    import_rva = struct.unpack_from("<I", data, optional + 112 + 8)[0]  # data directory 1: the import table
    table = optional + optional_size
    spans = [struct.unpack_from("<IIII", data, table + 40 * i + 8) for i in range(sections)]

    def at(rva: int) -> int:
        for size, address, _raw_size, raw in spans:
            if address <= rva < address + max(size, _raw_size):
                return rva - address + raw
        raise AssertionError(f"RVA {rva:#x} is in no section")

    names, entry = [], at(import_rva)
    while True:
        descriptor = struct.unpack_from("<IIIII", data, entry)
        if not any(descriptor):
            return names
        start = at(descriptor[3])
        names.append(data[start:data.index(b"\0", start)].decode("ascii"))
        entry += 20


# ---------------------------------------------------------------- programs linked with no C library

PICKED = {
    "hello": os.path.join(EXAMPLES, "hello"),
    "sum": os.path.join(EXAMPLES, "sum"),
    "factorial": os.path.join(EXAMPLES, "factorial"),
}
PICKED_CASES = ["02-types/integers", "05-functions/functions", "08-strings-collections/strings",
                "07-memory/region-list", "07-memory/trap-region-exhausted", "03-operators/trap-add-overflow",
                "10-errors/trap-stack-trace", "06-recursion/trap-recursion-depth",
                # stage 2: floating-point text, maps, sets, buffers, log lines
                "02-types/floats", "08-strings-collections/text-and-bytes", "08-strings-collections/collections",
                "08-strings-collections/text-sets", "08-strings-collections/trees", "19-stdlib/log"]


@needs_windows_cc
@pytest.mark.parametrize("name", sorted(PICKED) + PICKED_CASES)
def test_linked_without_libc_matches_the_jit(name, tmp_path):
    """18 Static linking, 16 Program startup: hello and programs of integers, text, floating-point numbers, regions,
    maps, sets, log lines, recursion, and traps, linked with the runtime in SemanticScript and no C library, print the
    same standard output and standard error (a trap's report and stack trace included) and exit with the same code as
    under `refined run`; the executable imports from KERNEL32.dll alone."""
    if name in PICKED:
        project = str(tmp_path / name)
        shutil.copytree(PICKED[name], project, ignore=shutil.ignore_patterns(".refined-cache"))
        args, stdin = (), ""
    else:
        case = CASES[name]
        project = caselib.materialize(case, str(tmp_path / "case"))
        args, stdin = case.args, case.stdin
    exe = os.path.join(project, "program.exe")
    built = _build(project, exe)
    assert built.returncode == 0, built.stdout + built.stderr
    assert "no C library" in built.stdout
    assert imported_dlls(exe) == ["KERNEL32.dll"]
    ran, jit = _exe(exe, project, args, stdin), _jit(project, args, stdin)
    assert (ran.returncode, ran.stdout, ran.stderr) == (jit.returncode, jit.stdout, jit.stderr)
    if name == "hello":
        assert ran.stdout == "Hello, world!\n" and ran.returncode == 0
    if name.split("/")[-1].startswith("trap-"):
        assert ran.returncode == 70 and ran.stderr.startswith("trap: ")
    if name == "10-errors/trap-stack-trace":
        assert "\n  in " in ran.stderr


@needs_windows_cc
def test_suite_programs_link_or_are_refused(tmp_path):
    """18 Static linking: every program case of the suite that runs either links with the runtime in SemanticScript
    and does exactly what its case says, or is refused when it is built (R901) because it needs runtime functions
    that runtime does not provide yet, named in the message; no executable is left behind for a refused one."""
    cases = [c for c in CASES.values() if c.mode in ("run", "trap") and not c.missing_tools()]

    def one(i: int) -> str:
        case = cases[i]
        project = caselib.materialize(case, str(tmp_path / str(i)))
        exe = os.path.join(project, "program.exe")
        built = _build(project, exe)
        if built.returncode != 0:
            assert "R901" in built.stdout and "does not provide yet" in built.stdout, (case.name, built.stdout)
            assert not os.path.exists(exe), case.name
            return "refused"
        proc = _exe(exe, project, case.args, case.stdin)
        expected = case.stdout if case.stdout is not None else ([] if not case.stdout_any else None)
        if case.mode == "run":
            assert proc.returncode == case.exit_code, (case.name, proc.stderr)
            assert case.stderr is None or proc.stderr.splitlines() == case.stderr, (case.name, proc.stderr)
        else:
            assert proc.returncode == 70 and case.detail in proc.stderr, (case.name, proc.stderr)
        assert expected is None or proc.stdout.splitlines() == expected, (case.name, proc.stdout)
        position = 0
        for wanted in case.stderr_contains:
            found = proc.stderr.find(wanted, position)
            assert found >= 0, (case.name, wanted, proc.stderr)
            position = found + len(wanted)
        return "linked"

    with ThreadPoolExecutor(6) as pool:
        outcomes = list(pool.map(one, range(len(cases))))
    # stage 1 linked 42 of the 76; stage 2 adds floating-point text and the host's buffers, maps, sets, and logs
    assert outcomes.count("linked") >= 49, outcomes.count("linked")


@needs_windows_cc
def test_program_needing_more_runtime_is_refused(tmp_path):
    """18 Static linking: a program that needs a host target the runtime in SemanticScript does not provide yet (here
    the clock, which is stage 3) is refused before linking, naming the targets, while the C runtime still builds it."""
    project = caselib.materialize(CASES["12-io/clock"], str(tmp_path / "clock"))
    exe = os.path.join(project, "program.exe")
    built = _build(project, exe)
    assert built.returncode != 0 and "R901" in built.stdout and "`clock.now`" in built.stdout, built.stdout
    assert "does not provide yet" in built.stdout and not os.path.exists(exe)
    with_c = caselib.refined("build", project, "--kind", "executable", "--output", exe)
    assert with_c.returncode == 0, with_c.stdout


# ---------------------------------------------------------------- floating-point text and the host library (stage 2)

@needs_windows_cc
def test_float_text_matches_python_over_a_large_table(tmp_path):
    """2 Floating-point numbers, 3 Floating-point precision, 22 Floating-point extremes, 18 Static linking (D-125,
    D-129): a program linked with the runtime in SemanticScript writes thousands of doubles (random bits, ordinary
    magnitudes, subnormals, every seventh power of two, powers of ten, values next to powers of two) exactly as
    Python's repr does, both with console.writeFloatLine and string.fromFloat64, and reads thousands of texts (shortest
    and 17- and 26-digit forms, exact halfway points between neighbouring doubles and texts a hair off them, long
    integers, texts too large or not numbers) exactly as Python's float() does; `refined run` uses both, so the
    executable agrees with it. The C runtime gives the same text."""
    formats, parses = floattable.format_values(7, 1500), floattable.parse_texts(11, 1500)
    project = str(tmp_path / "floats")
    floattable.write_project(project, formats, parses)
    caselib.approve(project)
    expected = floattable.expected_output(formats, parses)
    for runtime in ("semanticscript", "c"):
        exe = os.path.join(project, f"program-{runtime}.exe")
        built = caselib.refined("build", project, "--kind", "executable", "--runtime", runtime, "--output", exe)
        assert built.returncode == 0, built.stdout
        if runtime == "semanticscript":
            assert imported_dlls(exe) == ["KERNEL32.dll"]
        ran = _exe(exe, project)
        assert ran.returncode == 0 and ran.stderr == "", (runtime, ran.stderr)
        got = ran.stdout.splitlines()
        assert len(got) == len(expected), (runtime, len(got), len(expected))
        wrong = [(i, want, have) for i, (want, have) in enumerate(zip(expected, got)) if want != have]
        assert not wrong, (runtime, len(wrong), wrong[:10])


@needs_windows_cc
def test_host_targets_match_the_jit(tmp_path):
    """8 Strings, 8 Collections, 7 Memory regions, 19 Logging, 18 Static linking (D-130): a program that uses every
    host target the runtime in SemanticScript implements (buffers, string.fromBytes and text that is not UTF-8, maps of
    numbers with thousands of keys and removals, maps of text keys and values, maps of records holding text, sets of
    numbers and of text, every log level), twice so its regions and their host objects are released and made again,
    prints exactly what `refined run` prints, to both streams, and exits with the same code."""
    project = str(tmp_path / "tour")
    hosttour.write_project(project)
    caselib.approve(project)
    exe = os.path.join(project, "program.exe")
    built = _build(project, exe)
    assert built.returncode == 0, built.stdout
    assert imported_dlls(exe) == ["KERNEL32.dll"]
    ran, jit = _exe(exe, project), _jit(project)
    assert (ran.returncode, ran.stdout, ran.stderr) == (jit.returncode, jit.stdout, jit.stderr)
    assert ran.returncode == 0 and "[warn] a warning" in ran.stderr and "4000" in ran.stdout.splitlines()


def test_runtime_host_targets_are_the_c_runtimes():
    """D-130: every host target the runtime in SemanticScript dispatches over is one the C runtime and host.py
    implement, with the same scoped parameter; native.py reads the runtime's table to refuse any other (R901)."""
    import re
    from refined import host
    from refined.native import native_targets, runtime_host_targets
    ours, theirs = runtime_host_targets(), native_targets()
    assert len(ours) >= 25 and ours <= set(theirs) and ours <= set(host.HANDLERS), ours - set(theirs)
    with open(os.path.join(RUNTIME, "host.sem"), encoding="utf-8") as fh:
        text = fh.read()
    for name in ours:
        row = re.search(rf'^hostTargets cell (\w+) name "{re.escape(name)}"$', text, re.M).group(1)
        scoped = int(re.search(rf"^hostTargets cell {row} scoped (-?\d+)$", text, re.M).group(1))
        assert scoped == theirs[name], name


# ---------------------------------------------------------------- the runtime project

def test_runtime_project_checks_and_passes_its_tests():
    """20 Unit tests: the runtime project checks clean, its authority (`use machine.memory`, `use system.calls`)
    is approved, and its modules' tests pass under `refined test`, where machine and system targets run in the
    JIT's own process."""
    checked = caselib.refined("check", RUNTIME, "--no-cache")
    assert checked.returncode == 0 and checked.stdout.strip() == "ok", checked.stdout
    from refined.check import approved_authority, find_build
    assert approved_authority(find_build(RUNTIME)) == {"use machine.memory none", "use system.calls none"}
    if os.name != "nt":
        pytest.skip("the runtime's system targets are Windows functions")
    tested = caselib.refined("test", RUNTIME)
    assert tested.returncode == 0, tested.stdout + tested.stderr
    assert "41 of 41 tests passed" in tested.stdout


def test_runtime_sources_are_generated_from_their_dsl():
    """23 Code generation tools: the runtime's .sem files are exactly what tools/build.py writes from the DSL."""
    sys.path.insert(0, os.path.join(RUNTIME, "tools"))
    try:
        import build as runtime_build
    finally:
        sys.path.pop(0)
    for rel, text in runtime_build.generate().items():
        with open(os.path.join(RUNTIME, rel), encoding="utf-8", newline="") as fh:
            assert fh.read() == text, f"{rel} is stale: run semanticscript/runtime/tools/build.py"


# ---------------------------------------------------------------- the primitive layer's rules

def _module(body: str, imports=("standard.machine",)) -> str:
    rows = ["probe is module", 'probe purpose "A probe of the primitive layer"', "probe path probe"]
    rows += [f"probe imports {i}" for i in imports] + ["probe exports main", "", body]
    return "\n".join(rows) + "\n"


_MAIN = """main is operation
main purpose "Read the address 0 and exit"
main invariant none
main typeParameter none
main input none
main output ExitCode
main outputOwnedBy none
main raises none
main effect {effect}
main uses {uses}
main memoryHeap false
main async false
main maxRecursion none
main label begin loopKind none
main label begin within none
main let okCode ExitCode 0 immutable
main at begin do findZero
main at begin return ok okCode

findZero is call
findZero in main
findZero invokes machine.zero
findZero argument none
findZero result zeroAddress machine.Address
findZero ownedBy none
findZero cleanedBy none
findZero borrows none
findZero catch none
findZero suppresses none
"""
_CAPABILITY = """memoryAccess is capability
memoryAccess purpose "Authority to reach memory by address"
memoryAccess grants use machine.memory none
"""


def _project(root: str, text: str, allows: list[str] | None = None, approve: bool = True) -> str:
    os.makedirs(root, exist_ok=True)
    allow_rows = allows if allows is not None else allows_rows("probeProject", [text])
    rows = ["probeProject is project", 'probeProject purpose "A probe of the primitive layer"',
            "probeProject target console", 'probeProject version "0.1.0"', "probeProject language refined 1",
            "probeProject standardLibrary 1", *allow_rows, "probeProject requires none",
            "probeProject includesModule probe", "probeProject entry probe.main"]
    with open(os.path.join(root, "build.sem"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(rows) + "\n")
    with open(os.path.join(root, "probe.sem"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    if approve:
        caselib.approve(root)
    return root


def test_machine_targets_need_the_capability(tmp_path):
    """13 Capability escalation prevention, 17 Sandboxing: a `machine` target is refused unless the operation
    declares `effect use machine.memory` (R407) and uses a capability that grants it (R408), and build.sem allows
    it (R408); an allowed but unapproved `use machine.memory` stops `refined run` (D-53). With all of them the
    program runs."""
    no_effect = _project(str(tmp_path / "effect"), _module(_MAIN.format(effect="none", uses="none")))
    assert "R407" in "\n".join(caselib.diagnostics(no_effect))
    no_capability = _project(str(tmp_path / "uses"),
                             _module(_MAIN.format(effect="use machine.memory", uses="none")))
    assert "R408" in "\n".join(caselib.diagnostics(no_capability))
    granted = _module(_CAPABILITY + "\n" + _MAIN.format(effect="use machine.memory", uses="memoryAccess"))
    not_allowed = _project(str(tmp_path / "allows"), granted, allows=["probeProject allows none"])
    assert any("R408" in d and "build.sem does not allow" in d for d in caselib.diagnostics(not_allowed))
    unapproved = _project(str(tmp_path / "approve"), granted, approve=False)
    assert caselib.diagnostics(unapproved) == []
    refused = caselib.refined("run", unapproved, "--no-cache")
    assert refused.returncode == 3 and "allows use machine.memory none" in refused.stderr
    allowed = _project(str(tmp_path / "allowed"), granted)
    ran = caselib.refined("run", allowed, "--no-cache")
    assert ran.returncode == 0, ran.stdout + ran.stderr


def test_system_targets_need_the_capability(tmp_path):
    """13 Capability escalation prevention: a `system` target performs `use system.calls`, so an operation that
    calls one without declaring and being granted it is refused (R407)."""
    text = _module(_MAIN.format(effect="none", uses="none").replace("invokes machine.zero", "invokes system.getLastError")
                   .replace("result zeroAddress machine.Address", "result code Int32"), imports=("standard.system",))
    project = _project(str(tmp_path / "system"), text)
    found = "\n".join(caselib.diagnostics(project))
    assert "R407" in found and "use system.calls" in found


_ABI = """exported is operation
exported purpose "An operation exported to C"
exported invariant none
exported typeParameter none
exported input {input}
exported output {output}
exported outputOwnedBy none
exported raises {raises}
exported effect none
exported uses none
exported memoryHeap false
exported async false
exported maxRecursion none
exported abi c "{symbol}"
exported label begin loopKind none
exported label begin within none
exported let none
exported at begin return ok none
"""


@pytest.mark.parametrize("input_row,output,raises,symbol,code,words", [
    ("text String borrowed", "none", "none", "probe_text", "R403", "takes only"),
    ("none", "String", "none", "probe_string", "R403", "gives only"),
    ("none", "none", "console.WriteError", "probe_raises", "R402", "raises nothing"),
    ("none", "none", "none", "not-a-symbol", "R402", "is not a C symbol"),
])
def test_abi_rows_are_held_to_the_c_boundary(tmp_path, input_row, output, raises, symbol, code, words):
    """18 C interoperability, 18 Calling conventions: `abi c "<symbol>"` (D-123) exports only operations whose
    inputs and output cross the C boundary as they are, that raise nothing, under a C identifier."""
    body = _ABI.format(input=input_row, output=output, raises=raises, symbol=symbol)
    main = _MAIN.format(effect="none", uses="none").replace("main at begin do findZero\n", "") \
        .split("\nfindZero is call")[0] + "\n"
    imports = ("standard.console",) if raises != "none" else ("standard.machine",)
    text = _module(main + "\n" + body, imports=imports)
    if imports == ("standard.machine",):
        text = text.replace("probe imports standard.machine\n", "probe imports none\n")
    found = caselib.diagnostics(_project(str(tmp_path / "abi"), text))
    assert any(code in d and words in d for d in found), found


def test_abi_symbols_are_unique_and_optional(tmp_path):
    """18 C interoperability: a program names each C symbol once (R402); an operation has at most one `abi` row
    (R302), and one without it is an ordinary operation."""
    body = _ABI.format(input="none", output="none", raises="none", symbol="probe_one")
    twice = body + "\n" + body.replace("exported", "again")
    main = _MAIN.format(effect="none", uses="none").replace("main at begin do findZero\n", "") \
        .split("\nfindZero is call")[0] + "\n"
    text = _module(main + "\n" + twice, imports=()).replace("probe exports main", "probe imports none\nprobe exports main")
    found = caselib.diagnostics(_project(str(tmp_path / "unique"), text))
    assert any("R402" in d and "already the C symbol" in d for d in found), found
    doubled = _module(main + "\n" + body.replace('exported abi c "probe_one"\n',
                                                 'exported abi c "probe_one"\nexported abi c "probe_two"\n'),
                      imports=()).replace("probe exports main", "probe imports none\nprobe exports main")
    found = caselib.diagnostics(_project(str(tmp_path / "doubled"), doubled))
    assert any("R302" in d and "at most one" in d for d in found), found
