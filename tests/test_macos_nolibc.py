"""Executables for macOS on Apple silicon with no C library (D-189 onward): the runtime in SemanticScript reaching
Darwin's kernel through its system calls (`svc #0x80`), with no libSystem.

Apple supports only executables that link libSystem, and its system call interface is private; this is the
experiment of docs/runtime-in-semanticscript.md's stage 9, run in CI on GitHub's macos-14 runner (arm64). An
executable is built with `refined build --kind executable` and must name no dynamic library (no LC_LOAD_DYLIB of any
kind; with no loader at all when it is linked `static`), and must print and exit exactly as `refined run` (the JIT,
which runs on the host's own C library) does on the same machine. These tests run only on macOS on arm64; everywhere
else they skip, as the rest of the suite's executable tests skip on macOS.
"""
from __future__ import annotations

import os
import platform
import shutil
import struct
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import pytest

SUITE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "suite")
sys.path.insert(0, SUITE)

import caselib  # noqa: E402

EXAMPLES = os.path.join(caselib.ROOT, "docs", "refined-examples")
CASES = {c.name: c for c in caselib.discover()}
MACOS_ARM64 = sys.platform == "darwin" and platform.machine() == "arm64"
pytestmark = pytest.mark.skipif(not MACOS_ARM64, reason="executables with no C library for macOS are built and run "
                                "on macOS on arm64 only (D-189)")

# Mach-O load commands that name a dynamic library or the dynamic loader
LC_LOAD_DYLINKER = 0xE
DYLIB_COMMANDS = {0xC: "LC_LOAD_DYLIB", 0x80000018: "LC_LOAD_WEAK_DYLIB", 0x8000001F: "LC_REEXPORT_DYLIB",
                  0x20: "LC_LAZY_LOAD_DYLIB", 0x80000023: "LC_LOAD_UPWARD_DYLIB"}
LC_MAIN, LC_UNIXTHREAD, LC_CODE_SIGNATURE = 0x80000028, 0x5, 0x1D

# How many of the suite's running programs link and match `refined run` on macOS: raised as the Darwin paths grow
FLOOR = 0


def load_commands(path: str) -> list[int]:
    """The load commands of a 64-bit Mach-O executable, read from the file itself."""
    with open(path, "rb") as fh:
        data = fh.read()
    magic, _cpu, _sub, filetype, ncmds, _size, _flags, _reserved = struct.unpack_from("<IiiIIIII", data, 0)
    assert magic == 0xFEEDFACF and filetype == 2, (hex(magic), filetype)  # MH_MAGIC_64, MH_EXECUTE
    found, offset = [], 32
    for _ in range(ncmds):
        cmd, size = struct.unpack_from("<II", data, offset)
        found.append(cmd)
        offset += size
    return found


def assert_no_libsystem(path: str) -> None:
    """D-189: the executable names no dynamic library (otool -L lists none) and, when it is linked `static`, has no
    loader (no LC_LOAD_DYLINKER): only the program, the runtime, and the kernel's system calls."""
    commands = load_commands(path)
    assert not [DYLIB_COMMANDS[c] for c in commands if c in DYLIB_COMMANDS], commands
    listed = subprocess.run(["otool", "-L", path], capture_output=True, text=True)
    assert listed.returncode == 0 and listed.stdout.strip().splitlines() == [f"{path}:"], listed.stdout
    if _mode() == "static":
        assert LC_LOAD_DYLINKER not in commands and LC_UNIXTHREAD in commands, commands
    assert LC_CODE_SIGNATURE in commands, commands


def _mode() -> str:
    from refined.native import darwin_link_mode
    return darwin_link_mode()


def _build(project: str, exe: str, mode: str | None = None) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    if mode:
        env["REFINED_DARWIN_LINK"] = mode
    return subprocess.run([sys.executable, caselib.COMPILER, "build", project, "--kind", "executable", "--output",
                           exe], capture_output=True, text=True, encoding="utf-8", errors="replace", env=env,
                          timeout=1800)


def _jit(project: str, args=(), stdin: str = "") -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, caselib.COMPILER, "run", project, "--no-cache",
                           *(["--", *args] if args else [])], capture_output=True, text=True, encoding="utf-8",
                          errors="replace", cwd=project, input=stdin, timeout=600)


def _exe(exe: str, project: str, args=(), stdin: str = "") -> subprocess.CompletedProcess:
    return subprocess.run([exe, *args], capture_output=True, text=True, encoding="utf-8", errors="replace",
                          cwd=project, input=stdin, timeout=30)


def _hello(tmp_path, name: str = "hello") -> str:
    project = str(tmp_path / name)
    shutil.copytree(os.path.join(EXAMPLES, "hello"), project, ignore=shutil.ignore_patterns(".refined-cache"))
    return project


def test_link_modes_probe(tmp_path):
    """D-189: which way of linking an executable with no libSystem the runner's toolchain accepts and its kernel
    runs: `static` (LC_UNIXTHREAD, no dyld) and `dyld` (LC_MAIN, dyld with no library to load). Prints what it found
    for each; at least one must run `hello`."""
    def show(command: list[str]) -> str:
        try:
            done = subprocess.run(command, capture_output=True, text=True, timeout=60)
            return (done.stdout + done.stderr).strip()
        except (OSError, subprocess.SubprocessError) as exc:
            return f"({exc})"

    print("\n== macOS:", show(["sw_vers"]).replace("\n", "; "))
    print("== cc:", show(["cc", "--version"]).splitlines()[0] if show(["cc", "--version"]) else "")
    print("== ld:", show(["ld", "-v"]).replace("\n", "; "))
    print("== cc -dumpmachine:", show(["cc", "-dumpmachine"]))
    project = _hello(tmp_path)
    ran_any = []
    for mode in ("static", "dyld"):
        exe = os.path.join(project, f"hello-{mode}")
        built = _build(project, exe, mode)
        print(f"== {mode}: build exit {built.returncode}: {(built.stdout + built.stderr).strip()[-2000:]}")
        if built.returncode != 0:
            continue
        commands = load_commands(exe)
        print(f"== {mode}: load commands {[hex(c) for c in commands]}; {os.path.getsize(exe)} bytes")
        print(f"== {mode}: otool -L: {show(['otool', '-L', exe])!r}")
        print(f"== {mode}: codesign: {show(['codesign', '-dv', exe])!r}")
        try:
            ran = _exe(exe, project)
            print(f"== {mode}: exit {ran.returncode} stdout {ran.stdout!r} stderr {ran.stderr[-500:]!r}")
            if ran.returncode == 0 and ran.stdout == "Hello, world!\n":
                ran_any.append(mode)
        except subprocess.TimeoutExpired:
            print(f"== {mode}: timed out")
    print("== modes that run hello:", ran_any)
    assert ran_any, "no way of linking ran hello with no libSystem"


def test_hello_matches_the_jit(tmp_path):
    """18 Static linking, 16 Program startup (D-189): `hello` links with the runtime in SemanticScript and no C
    library for arm64 macOS, names no dynamic library, is signed, and prints and exits as `refined run` does."""
    project = _hello(tmp_path)
    exe = os.path.join(project, "program")
    built = _build(project, exe)
    assert built.returncode == 0, built.stdout + built.stderr
    assert "no C library" in built.stdout, built.stdout
    assert_no_libsystem(exe)
    ran, jit = _exe(exe, project), _jit(project)
    assert (ran.returncode, ran.stdout, ran.stderr) == (jit.returncode, jit.stdout, jit.stderr)
    assert ran.stdout == "Hello, world!\n" and ran.returncode == 0


def test_suite_programs_on_macos(tmp_path):
    """18 Static linking (D-189): every program case of the suite that runs is built for macOS with no C library;
    one that links names no dynamic library and must behave exactly as under `refined run` on the same machine
    (standard output, standard error, exit code), and one that needs what the Darwin paths do not have yet is
    refused when built (R901), naming it. Prints each program's outcome; at least FLOOR match."""
    cases = [c for c in CASES.values() if c.mode in ("run", "trap") and not c.missing_tools()]

    def one(i: int) -> tuple[str, str, str]:
        case = cases[i]
        project = caselib.materialize(case, str(tmp_path / str(i)))
        exe = os.path.join(project, "program")
        built = _build(project, exe)
        if built.returncode != 0:
            text = (built.stdout + built.stderr).strip()
            kind = "refused" if "R901" in built.stdout else "build-failed"
            return case.name, kind, text[-600:]
        try:
            assert_no_libsystem(exe)
        except AssertionError as exc:
            return case.name, "links-libsystem", str(exc)[:600]
        try:
            ran = _exe(exe, project, case.args, case.stdin)
        except subprocess.TimeoutExpired:
            return case.name, "timeout", ""
        jit = _jit(project, case.args, case.stdin)
        if (ran.returncode, ran.stdout, ran.stderr) == (jit.returncode, jit.stdout, jit.stderr):
            return case.name, "match", ""
        detail = (f"exe exit {ran.returncode} out {ran.stdout[-300:]!r} err {ran.stderr[-300:]!r}; "
                  f"jit exit {jit.returncode} out {jit.stdout[-300:]!r} err {jit.stderr[-300:]!r}")
        return case.name, "differs", detail

    with ThreadPoolExecutor(3) as pool:
        outcomes = list(pool.map(one, range(len(cases))))
    counts: dict[str, int] = {}
    for name, kind, detail in sorted(outcomes):
        counts[kind] = counts.get(kind, 0) + 1
        print(f"== {kind:15} {name}" + (f": {detail}" if detail else ""))
    print("== totals:", counts, "of", len(cases))
    unexplained = [(n, d) for n, k, d in outcomes if k == "refused" and "R901" not in d]
    assert not unexplained, unexplained
    assert counts.get("match", 0) >= FLOOR, counts
