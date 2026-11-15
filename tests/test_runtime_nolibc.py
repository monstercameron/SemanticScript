"""The runtime in SemanticScript, stages 1 to 5 (docs/runtime-in-semanticscript.md, D-120 to D-143).

`refined build --kind executable` links a program with the runtime project in semanticscript/runtime and no C
library, on Windows and on x86_64 Linux; it is the only runtime (D-141). These tests hold it to the bar's first parts: what links behaves exactly
as `refined run` does (output, exit code, trap report), the executable imports from KERNEL32.dll alone, a program
that needs what the runtime does not provide yet is refused before linking, the runtime project checks and passes
its own tests, and the primitive layer (`machine`, `system`, `abi c`) is held to its rules by the checker. Stage 2
adds floating-point text (checked against Python, which `refined run` uses, over a large table of values) and the
host library's buffers, maps, sets, string.fromBytes, and log lines (checked against `refined run`). Stages 3 and 4
add files, directories, claims, scopes, the environment, arguments, standard input, child processes and pipes, time,
tasks on fibers, groups, cancellation, channels, and deadlocks: every running suite program but those that need what
no executable runtime has, every conformance program, the stage0 samples, and the warehouse example link and match
`refined run`, and the runtime and the program are linked as one module, so an executable holds only what it uses."""
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


def _platform() -> str:
    """`windows` or `linux` when this machine's C compiler can link the runtime in SemanticScript (MinGW on Windows,
    x86_64 Linux), otherwise empty."""
    from refined.native import find_cc, platform
    cc = find_cc()
    if cc is None:
        return ""
    _machine, triple, _problem = platform(cc)
    if triple is None:
        return ""
    return "windows" if "windows" in triple else "linux"


PLATFORM = _platform()
WINDOWS = PLATFORM == "windows"
needs_windows_cc = pytest.mark.skipif(not PLATFORM, reason="the runtime in SemanticScript links on Windows (MinGW) "
                                      "and x86_64 Linux")


def _build(project: str, exe: str) -> subprocess.CompletedProcess:
    return caselib.refined("build", project, "--kind", "executable", "--output", exe)


def _jit(project: str, args=(), stdin: str = "") -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, caselib.COMPILER, "run", project, "--no-cache",
                           *(["--", *args] if args else [])], capture_output=True, text=True, encoding="utf-8",
                          errors="replace", cwd=project, input=stdin, timeout=300)


def _exe(exe: str, project: str, args=(), stdin: str = "") -> subprocess.CompletedProcess:
    return subprocess.run([exe, *args], capture_output=True, text=True, encoding="utf-8", errors="replace",
                          cwd=project, input=stdin, timeout=120)


def elf_dynamic(path: str) -> list[int]:
    """The program headers of an ELF executable that ask for a dynamic loader: PT_DYNAMIC (2) and PT_INTERP (3),
    read from the file itself; none for a static executable."""
    with open(path, "rb") as fh:
        data = fh.read()
    assert data[:4] == b"\x7fELF" and data[4] == 2, "a 64-bit ELF file"
    phoff = struct.unpack_from("<Q", data, 0x20)[0]
    phentsize, phnum = struct.unpack_from("<HH", data, 0x36)
    types = [struct.unpack_from("<I", data, phoff + i * phentsize)[0] for i in range(phnum)]
    return [t for t in types if t in (2, 3)]


def assert_no_libc(path: str) -> None:
    """Bar point 2: Windows, the import table names KERNEL32.dll alone; Linux, no dynamic section or interpreter and
    nothing of the C library in the file."""
    if WINDOWS:
        assert imported_dlls(path) == ["KERNEL32.dll"]
        return
    assert elf_dynamic(path) == [], elf_dynamic(path)
    with open(path, "rb") as fh:
        data = fh.read()
    for mark in (b"libc.so", b"GLIBC_", b"ld-linux", b"__libc_start_main"):
        assert mark not in data, mark


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
                "08-strings-collections/text-sets", "08-strings-collections/trees", "19-stdlib/log",
                # stages 3 and 4: files, claims, scopes, the environment, arguments, standard input, child processes,
                # time, tasks, groups, cancellation, and channels
                "07-memory/resources", "12-io/file-write", "12-io/directories", "19-stdlib/file-lock",
                "17-security/trap-computed-path-escape", "12-io/arguments", "12-io/environment", "12-io/stdin",
                "12-io/process-run", "17-security/trap-computed-program", "12-io/clock", "11-concurrency/parallel",
                "11-concurrency/cancellation", "11-concurrency/tasks-and-channels",
                # secrets, crypto, and foreign libraries (D-137)
                "19-stdlib/secret", "19-stdlib/crypto", "18-interop/foreign"]


@needs_windows_cc
@pytest.mark.parametrize("name", sorted(PICKED) + PICKED_CASES)
def test_linked_without_libc_matches_the_jit(name, tmp_path):
    """18 Static linking, 16 Program startup: hello and programs of integers, text, floating-point numbers, regions,
    maps, sets, log lines, recursion, and traps, linked with the runtime in SemanticScript and no C library, print the
    same standard output and standard error (a trap's report and stack trace included) and exit with the same code as
    under `refined run`; the executable imports from KERNEL32.dll alone."""
    if name in REFUSED:
        pytest.skip(f"{name} needs `{REFUSED[name]}`, which an executable here does not have")
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
    assert_no_libc(exe)
    ran, jit = _exe(exe, project, args, stdin), _jit(project, args, stdin)
    assert (ran.returncode, ran.stdout, ran.stderr) == (jit.returncode, jit.stdout, jit.stderr)
    if name == "hello":
        assert ran.stdout == "Hello, world!\n" and ran.returncode == 0
    if name.split("/")[-1].startswith("trap-"):
        assert ran.returncode == 70 and ran.stderr.startswith("trap: ")
    if name == "10-errors/trap-stack-trace":
        assert "\n  in " in ran.stderr


# What the runtime in SemanticScript does not implement (D-137): sockets (Winsock is not kernel32), HTTP requests,
# JSON, random numbers, and interrupts stay under `refined run`; each of these programs needs one of them.
REFUSED = {"12-io/network-connect": "net", "19-stdlib/json": "json", "19-stdlib/library-tour": "http",
           "19-stdlib/random": "random", "19-stdlib/signal": "signal"}
if not WINDOWS:  # D-140: a foreign library needs the C library's dynamic loader
    REFUSED["18-interop/foreign"] = "ffi"


@needs_windows_cc
def test_suite_programs_link_or_are_refused(tmp_path):
    """18 Static linking: every program case of the suite that runs links with the runtime in SemanticScript and does
    exactly what its case says, but those that need a host target no executable runtime has, which are refused when
    they are built (R901), naming the targets; no executable is left behind for a refused one."""
    cases = [c for c in CASES.values() if c.mode in ("run", "trap") and not c.missing_tools()]

    def one(i: int) -> str:
        case = cases[i]
        project = caselib.materialize(case, str(tmp_path / str(i)))
        exe = os.path.join(project, "program.exe")
        built = _build(project, exe)
        if built.returncode != 0:
            assert "R901" in built.stdout and "does not provide yet" in built.stdout, (case.name, built.stdout)
            assert f"`{REFUSED.get(case.name, '?')}." in built.stdout, (case.name, built.stdout)
            assert not os.path.exists(exe), case.name
            return "refused:" + case.name
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
    # stage 1 linked 42 of the 76, stage 2 49; stages 3 and 4 every program but the five REFUSED names
    refused = {o.split(":", 1)[1] for o in outcomes if o.startswith("refused:")}
    assert refused == set(REFUSED) & {c.name for c in cases}, refused
    # 71 on Windows; 70 on Linux, where `18-interop/foreign` is refused too (ffi needs the dynamic loader, D-140)
    assert outcomes.count("linked") == len(cases) - len(refused) >= (71 if WINDOWS else 70), outcomes.count("linked")


@needs_windows_cc
def test_program_needing_more_runtime_is_refused(tmp_path):
    """18 Static linking: a program that needs a host target the runtime in SemanticScript does not provide (here
    JSON, D-137) is refused before linking, naming the targets; `--runtime semanticscript`, still accepted (D-141),
    changes nothing."""
    project = caselib.materialize(CASES["19-stdlib/json"], str(tmp_path / "json"))
    exe = os.path.join(project, "program.exe")
    built = _build(project, exe)
    assert built.returncode != 0 and "R901" in built.stdout and "`json.parse`" in built.stdout, built.stdout
    assert "does not provide yet" in built.stdout and not os.path.exists(exe)
    compatible = caselib.refined("build", project, "--kind", "executable", "--runtime", "semanticscript", "--output",
                                 exe)
    assert compatible.returncode != 0 and compatible.stdout == built.stdout, compatible.stdout


# ---------------------------------------------------------------- floating-point text and the host library (stage 2)

@needs_windows_cc
def test_float_text_matches_python_over_a_large_table(tmp_path):
    """2 Floating-point numbers, 3 Floating-point precision, 22 Floating-point extremes, 18 Static linking (D-125,
    D-129): a program linked with the runtime in SemanticScript writes thousands of doubles (random bits, ordinary
    magnitudes, subnormals, every seventh power of two, powers of ten, values next to powers of two) exactly as
    Python's repr does, both with console.writeFloatLine and string.fromFloat64, and reads thousands of texts (shortest
    and 17- and 26-digit forms, exact halfway points between neighbouring doubles and texts a hair off them, long
    integers, texts too large or not numbers) exactly as Python's float() does; `refined run` uses both, so the
    executable agrees with it."""
    formats, parses = floattable.format_values(7, 1500), floattable.parse_texts(11, 1500)
    project = str(tmp_path / "floats")
    floattable.write_project(project, formats, parses)
    caselib.approve(project)
    expected = floattable.expected_output(formats, parses)
    exe = os.path.join(project, "program.exe")
    built = _build(project, exe)
    assert built.returncode == 0, built.stdout
    assert_no_libc(exe)
    ran = _exe(exe, project)
    assert ran.returncode == 0 and ran.stderr == "", ran.stderr
    got = ran.stdout.splitlines()
    assert len(got) == len(expected), (len(got), len(expected))
    wrong = [(i, want, have) for i, (want, have) in enumerate(zip(expected, got)) if want != have]
    assert not wrong, (len(wrong), wrong[:10])


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
    assert_no_libc(exe)
    ran, jit = _exe(exe, project), _jit(project)
    assert (ran.returncode, ran.stdout, ran.stderr) == (jit.returncode, jit.stdout, jit.stderr)
    assert ran.returncode == 0 and "[warn] a warning" in ran.stderr and "4000" in ran.stdout.splitlines()


# ---------------------------------------------------------------- stages 3 and 4: examples, conformance, size

def _same_as_jit(project: str, args=(), stdin: str = "") -> tuple:
    """Build `project` with the runtime in SemanticScript and run it and `refined run`; (executable, JIT) results,
    the project's path written `<project>` in standard error."""
    exe = os.path.join(project, "program.exe")
    built = _build(project, exe)
    assert built.returncode == 0, built.stdout + built.stderr
    assert_no_libc(exe)
    ran, jit = _exe(exe, project, args, stdin), _jit(project, args, stdin)
    where = os.path.normpath(project)
    return ((ran.returncode, ran.stdout, ran.stderr.replace(where, "<project>")),
            (jit.returncode, jit.stdout, jit.stderr.replace(where, "<project>")))


WAREHOUSE_EDITS = {"good": None, "duplicate": ("order cell gadget sku 102", "order cell gadget sku 101"),
                   "cycle": ("components cell kitWidgets partSku 101", "components cell kitWidgets partSku 300"),
                   "invalid": ("order cell gadget quantity 2", "order cell gadget quantity -2"),
                   "unknown": ("order cell gizmo sku 103", "order cell gizmo sku 999")}


@needs_windows_cc
@pytest.mark.parametrize("variant", sorted(WAREHOUSE_EDITS))
def test_warehouse_example_without_libc(tmp_path, variant):
    """Roadmap 1 to 3, 11 Structured concurrency, 18 Static linking: the warehouse example (bundles through the bill
    of materials, a map of category subtotals, a set that rejects a repeated SKU, two pricing tasks, files) linked with
    the runtime in SemanticScript imports KERNEL32.dll alone and prints, fails, and exits exactly as under `refined
    run`, on its good path and each failure path: a repeated SKU (8), a bundle that holds itself (9), an invalid line
    that fails both tasks (2, the second failure on standard error), an unknown SKU (7)."""
    project = str(tmp_path / variant)
    shutil.copytree(os.path.join(EXAMPLES, "warehouse"), project, ignore=shutil.ignore_patterns(".refined-cache"))
    edit = WAREHOUSE_EDITS[variant]
    if edit is not None:
        path = os.path.join(project, "warehouse.sem")
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        assert text.count(edit[0]) == 1, edit
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text.replace(*edit))
    ran, jit = _same_as_jit(project)
    assert ran == jit
    assert ran[0] == {"good": 0, "duplicate": 8, "cycle": 9, "invalid": 2, "unknown": 7}[variant], ran
    if variant == "good":
        assert ran[1].splitlines()[-1] == "list=5625 discounted=5062"
    if variant == "invalid":
        assert "the discount total failed too" in ran[2]


@needs_windows_cc
def test_conformance_programs_without_libc(tmp_path):
    """18 Static linking, 11 Structured concurrency, 13 Capabilities: every conformance check that runs a program,
    the group whose first failure cancels a ten-second sleep included (tasks wait on fibers, D-133), behaves under
    the runtime in SemanticScript exactly as under `refined run`: output, errors, and exit code."""
    sys.path.insert(0, SUITE)
    import conformance
    checks = [c for g in conformance.GUARANTEES for c in g.checks if c.kind in ("run", "trap")]

    def one(i: int):
        check = checks[i]
        project = str(tmp_path / str(i) / check.base)
        shutil.copytree(conformance.BASES[check.base], project)
        for file, old, new in check.edits:
            path = os.path.join(project, file)
            with open(path, encoding="utf-8", newline="") as fh:
                text = fh.read()
            text = (text.rstrip("\n") + "\n\n" + new.strip("\n") + "\n") if old == "<append>" else text.replace(old, new)
            with open(path, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(text)
        ran, jit = _same_as_jit(project, check.args)
        return check.id, ran, jit

    with ThreadPoolExecutor(6) as pool:
        results = list(pool.map(one, range(len(checks))))
    wrong = [(cid, ran, jit) for cid, ran, jit in results if ran != jit]
    assert not wrong, wrong[:3]
    assert len(results) >= 15 and "group-first-failure" in {cid for cid, _r, _j in results}


@needs_windows_cc
def test_stage0_samples_without_libc(tmp_path):
    """18 Static linking: every sample stage0 compiles, built instead by `refined build` with the runtime in
    SemanticScript, does exactly what it does under `refined run`."""
    samples = os.path.join(EXAMPLES, "stage0", "samples")
    names = [n for n in sorted(os.listdir(samples)) if os.path.exists(os.path.join(samples, n, "build.sem"))
             and n not in ("refused", "outside")]

    def one(name: str):
        project = str(tmp_path / name)
        shutil.copytree(os.path.join(samples, name), project, ignore=shutil.ignore_patterns(".refined-cache", "build"))
        return (name, *_same_as_jit(project))

    with ThreadPoolExecutor(6) as pool:
        results = list(pool.map(one, names))
    wrong = [r for r in results if r[1] != r[2]]
    assert not wrong, wrong[:3]
    assert len(results) >= 20


@needs_windows_cc
def test_stage0_compiler_without_libc(tmp_path, stage0_native):
    """Roadmap, D-142: stage0, the compiler written in SemanticScript, is an executable with no C library, and the
    executables it builds link the runtime in SemanticScript as an object with no C library too, and do what their
    samples do under `refined run`."""
    from conftest import LINK, c_compiler
    from test_stage0 import SAMPLES
    assert_no_libc(stage0_native)
    stage0 = os.path.join(EXAMPLES, "stage0")
    for sample in ("hello", "maps", "files", "lists"):
        work = str(tmp_path / sample)
        shutil.copytree(stage0, work, ignore=shutil.ignore_patterns("build", ".refined-cache"))
        proc = subprocess.run([stage0_native, f"samples/{sample}", f"build/{sample}", c_compiler(), *LINK],
                              capture_output=True, text=True, cwd=work, timeout=600)
        assert proc.returncode == 0, (sample, proc.stdout, proc.stderr)
        built = os.path.join(work, "build", sample + (".exe" if os.name == "nt" else ""))
        assert_no_libc(built)
        ran = subprocess.run([built], capture_output=True, text=True, cwd=work, timeout=60)
        assert (ran.stdout, ran.returncode) == SAMPLES[sample], (sample, ran.stderr)


@needs_windows_cc
def test_executables_link_no_c_library(tmp_path):
    """Bar point 2 (D-124, D-139): an executable links no C library. On Windows its import table names KERNEL32.dll
    alone; on Linux it is a static ELF file with no dynamic section and no interpreter, and nothing of the C library
    is in it. The runtime object stage0 links (`--kind runtime`) defines `refined_entry` and leaves only the
    program's `refined_program_main` for the C to define."""
    hello = str(tmp_path / "hello")
    shutil.copytree(PICKED["hello"], hello, ignore=shutil.ignore_patterns(".refined-cache"))
    exe = os.path.join(hello, "program.exe")
    built = _build(hello, exe)
    assert built.returncode == 0 and "no C library" in built.stdout, built.stdout
    assert_no_libc(exe)
    if not WINDOWS:
        assert elf_dynamic(exe) == []
    obj = str(tmp_path / "runtime.o")
    made = caselib.refined("build", RUNTIME, "--kind", "runtime", "--output", obj)
    assert made.returncode == 0 and os.path.getsize(obj) > 0, made.stdout
    with open(obj, "rb") as fh:
        data = fh.read()
    assert b"refined_entry" in data and b"refined_program_main" in data


@needs_windows_cc
def test_executables_hold_only_what_they_use(tmp_path):
    """D-135: the runtime and the program are compiled into one module whose functions are all internal but the
    entry, and what the entry never reaches is dropped, so `hello` is a few tens of kilobytes (it was 145 KB when the
    whole runtime object was linked) while a program using tasks, files, and maps is larger."""
    hello = str(tmp_path / "hello")
    shutil.copytree(PICKED["hello"], hello, ignore=shutil.ignore_patterns(".refined-cache"))
    ran, jit = _same_as_jit(hello)
    assert ran == jit and ran[1] == "Hello, world!\n"
    small = os.path.getsize(os.path.join(hello, "program.exe"))
    assert small < 48 * 1024, small
    project = caselib.materialize(CASES["11-concurrency/parallel"], str(tmp_path / "parallel"))
    ran, jit = _same_as_jit(project)
    assert ran == jit and os.path.getsize(os.path.join(project, "program.exe")) > small


def test_runtime_host_targets_cover_the_library():
    """D-130, D-136, D-137, D-143: the runtime in SemanticScript dispatches over every host target host.py implements
    but those of `net`, `http`, `json`, `random`, and `signal` (and on Linux `ffi`, D-140), with the scoped parameter
    host.py checks (D-38); native.py reads the runtime's table to refuse any other (R901)."""
    import re
    from refined import host
    from refined.native import runtime_host_targets
    ours = runtime_host_targets()
    assert ours <= set(host.HANDLERS), ours - set(host.HANDLERS)
    missing = {name.split(".")[0] for name in set(host.HANDLERS) - ours}
    assert missing == {"net", "http", "json", "random", "signal"}, missing
    linux = runtime_host_targets("x86_64-unknown-linux-gnu")
    assert ours - linux == {"ffi.open", "ffi.close", "ffi.Function.bind"}, ours - linux
    with open(os.path.join(RUNTIME, "host.sem"), encoding="utf-8") as fh:
        text = fh.read()
    for name in ours:
        row = re.search(rf'^hostTargets cell (\w+) name "{re.escape(name)}"$', text, re.M).group(1)
        scoped = int(re.search(rf"^hostTargets cell {row} scoped (-?\d+)$", text, re.M).group(1))
        assert scoped == host.SCOPED.get(name, -1), name


# ---------------------------------------------------------------- the runtime project

def test_runtime_project_checks_and_passes_its_tests():
    """20 Unit tests: the runtime project checks clean, its authority (`use machine.memory`, `use system.calls`)
    is approved, and its modules' tests pass under `refined test`, where machine and system targets run in the
    JIT's own process."""
    checked = caselib.refined("check", RUNTIME, "--no-cache")
    assert checked.returncode == 0 and checked.stdout.strip() == "ok", checked.stdout
    from refined.check import approved_authority, find_build
    assert approved_authority(find_build(RUNTIME)) == {"use machine.memory none", "use system.calls none"}
    from refined.runtime import default_triple
    triple = default_triple()
    if os.name != "nt" and not (triple.startswith("x86_64") and "linux" in triple):
        pytest.skip("the runtime's system targets are Windows functions and x86_64 Linux system calls")
    tested = caselib.refined("test", RUNTIME)
    assert tested.returncode == 0, tested.stdout + tested.stderr
    assert "60 of 60 tests passed" in tested.stdout


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
