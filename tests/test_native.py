"""The native host library (D-80 to D-85): standalone executables run programs that use files, arguments, the
environment, standard input, child processes, deadlines, buffers, maps, and sets, and behave exactly as
`refined run` does: the same standard output, the same standard error, the same exit code, the same files.

Each probe program below calls one library target per step and prints what happened (the result, or the error
variant and its payload), so a difference in any variant or payload shows up as a different line."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import pytest

SUITE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "suite")
sys.path.insert(0, SUITE)

import caselib  # noqa: E402
import sembuild as sb  # noqa: E402
from caselib import allows_rows  # noqa: E402

EXAMPLES = os.path.join(caselib.ROOT, "docs", "refined-examples")


def _has_cc() -> bool:
    from refined.native import find_cc
    return find_cc() is not None


needs_cc = pytest.mark.skipif(not _has_cc(), reason="linking an executable needs a C compiler")


def _project(root: str, module: str, text: str) -> str:
    """A console project holding one module, with exactly the authority the module asks for, approved."""
    os.makedirs(root, exist_ok=True)
    rows = [f"{module}Project is project", f'{module}Project purpose "A native host library probe"',
            f"{module}Project target console", f'{module}Project version "0.1.0"',
            f"{module}Project language refined 1", f"{module}Project standardLibrary 1",
            *allows_rows(f"{module}Project", [text]), f"{module}Project requires none",
            f"{module}Project includesModule {module}", f"{module}Project entry {module}.main"]
    with open(os.path.join(root, "build.sem"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(rows) + "\n")
    with open(os.path.join(root, f"{module}.sem"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    caselib.approve(root)
    assert not caselib.diagnostics(root), "\n".join(caselib.diagnostics(root))
    return root


def _files(folder: str) -> dict[str, bytes]:
    out = {}
    for base, dirs, files in os.walk(folder):
        dirs[:] = [d for d in dirs if d != ".refined-cache"]
        for f in files:
            if f.endswith((".exe", ".sem", ".approved")) or f == "program":
                continue
            path = os.path.join(base, f)
            with open(path, "rb") as fh:
                out[os.path.relpath(path, folder)] = fh.read()
        for d in dirs:
            out[os.path.relpath(os.path.join(base, d), folder) + os.sep] = b""
    return out


def both(project: str, args=(), stdin: str = "", env=None) -> tuple:
    """Run `project` under the JIT and as an executable, each in its own copy of the project; return both
    outcomes as (exit code, stdout, stderr with the project's folder written `<project>`, files left behind)."""
    jit_dir, exe_dir = project + "-jit", project + "-exe"
    shutil.copytree(project, jit_dir)
    shutil.copytree(project, exe_dir)
    exe = os.path.join(exe_dir, "program" + (".exe" if os.name == "nt" else ""))
    built = caselib.refined("build", exe_dir, "--kind", "executable", "--output", exe)
    assert built.returncode == 0, built.stdout + built.stderr
    environment = {**os.environ, **(env or {})}
    jit = subprocess.run([sys.executable, caselib.COMPILER, "run", jit_dir, "--no-cache", *(["--", *args] if args
                         else [])], capture_output=True, cwd=jit_dir, input=stdin.encode(), env=environment,
                         timeout=300)
    ran = subprocess.run([exe, *args], capture_output=True, cwd=exe_dir, input=stdin.encode(), env=environment,
                         timeout=300)

    def outcome(proc, folder):
        err = proc.stderr.decode("utf-8", "replace")
        for spelled in {folder, os.path.normpath(folder), os.path.realpath(folder)}:
            err = err.replace(spelled, "<project>")
        return proc.returncode, proc.stdout.decode("utf-8", "replace"), err, _files(folder)
    return outcome(jit, jit_dir), outcome(ran, exe_dir)


# ---------------------------------------------------------------- probe programs

class Probe:
    """One `main` that runs steps in order. A step calls one target; on success it prints its result (if asked),
    on failure the error's variant and payload; either way the next step runs."""

    def __init__(self, module: str, imports: tuple[str, ...] = ()):
        self.module = module
        self.imports = {"console", *imports}
        self.prog = sb.Prog(module, "Probe library targets one step at a time")
        self.prog.add(sb.STDOUT_CAP)
        self.shown: set[str] = set()
        self.steps: list[tuple[str, str]] = []
        self.lets: list[str] = ["okCode ExitCode 0 immutable"]
        self.entities: list[str] = []
        self.effects: set[str] = {"write console.stdout"}
        self.uses: set[str] = {"stdoutWriter"}
        self.waits = False
        self.finishes = False
        self.n = 0
        self.texts: dict[str, str] = {}

    def text(self, value: str) -> str:
        if value not in self.texts:
            name = f"text{len(self.texts)}"
            self.texts[value] = name
            self.lets.append(f'{name} String "{value}" immutable')
        return self.texts[value]

    def let(self, row: str) -> str:
        self.lets.append(row)
        return row.split()[0]

    def capability(self, name: str, grants: list[str]) -> None:
        rows = [f"{name} is capability", f'{name} purpose "Authority a probe step needs"']
        rows += [f"{name} grants {g}" for g in grants]
        self.prog.add("\n".join(rows))
        self.uses.add(name)
        for g in grants:
            self.effects.add(" ".join(g.split()[:2]))

    def _print(self, label: str, typ: str, value: str) -> None:
        self.n += 1
        target, slot, mode = sb.SHOW[typ]
        self.shown.add(typ)
        name = f"say{self.n}"
        self.entities.append(sb.call(name, "main", target, (f"{slot} {typ} {value} {mode}",)))
        self.steps.append((label, f"do {name}"))

    def step(self, target: str, args: list[str], catch: str | None = None, out: str | None = None,
             owned: str = "none", task: bool = False, show: str | None = None, borrows: str = "none",
             needed: bool = False) -> str | None:
        """`needed`: a later step uses the result, so a failure ends the program (after printing it)."""
        from refined.library import LIBRARY
        i = len([s for s in self.steps if s[1].startswith(("do c", "start c"))])
        here, ok, bad, after = ("begin" if i == 0 else f"p{i}"), f"k{i}", f"e{i}", f"p{i + 1}"
        call = f"c{i}"
        catch_row = f"err{i} {catch}" if catch else "none"
        if target.split(".")[0] in LIBRARY:
            self.imports.add(target.split(".")[0])
        if catch:
            self.imports.add(catch.split(".")[0])
        self.entities.append(sb.call(call, "main", target, args, out=f"{out}" if out else "none", owned=owned,
                                     catch=catch_row, kind="task" if task else "call", borrows=borrows))
        if task:
            self.waits = True
            self.steps += [(here, f"start {call} into none"), (here, f"join {call}")]
        else:
            self.steps.append((here, f"do {call}"))
        if catch:
            self.steps.append((here, f"branch ifError {call} goto {bad} else goto {ok}"))
        else:
            self.steps.append((here, f"goto {ok}"))
        if show:
            self._print(ok, show, out.split()[0])
        else:
            self._print(ok, "String", self.text(f"{call} ok"))
        self.steps.append((ok, f"goto {after}"))
        if catch:
            from refined.library import LIBRARY
            mod, name = catch.split(".", 1)
            variants = LIBRARY[mod]["types"][name].variants
            self.steps.append((bad, f"match err{i} {catch}"))
            for v, payload in variants:
                lab = f"{bad}{v}"
                bind = f"pay{i}{v} {payload}" if payload else "none none"
                self.steps.append((bad, f"case {catch}.{v} bind {bind} goto {lab}"))
            for v, payload in variants:
                lab = f"{bad}{v}"
                self._print(lab, "String", self.text(f"{call} {v}"))
                if payload == "Int64":
                    self._print(lab, "Int64", f"pay{i}{v}")
                elif payload == "Int32":
                    self.imports.add("convert")
                    self.n += 1
                    widen = f"widen{self.n}"
                    self.entities.append(sb.call(widen, "main", "convert.int32ToInt64",
                                                 (f"value Int32 pay{i}{v} copy",), out=f"wide{self.n} Int64"))
                    self.steps.append((lab, f"do {widen}"))
                    self._print(lab, "Int64", f"wide{self.n}")
                self.steps.append((lab, f"goto {'finish' if needed else after}"))
            self.finishes = self.finishes or needed
        return out.split()[0] if out else None

    def render(self) -> str:
        last = len([s for s in self.steps if s[1].startswith(("do c", "start c"))])
        steps = self.steps + [("begin" if last == 0 else f"p{last}", "return ok okCode")]
        if self.finishes:
            steps.append(("finish", "return ok okCode"))
        self.prog.add(sb.op("main", "Run each probe step in order", steps, output="ExitCode",
                            effects=tuple(sorted(self.effects)), uses=tuple(sorted(self.uses)), heap=True,
                            waits=self.waits, lets=tuple(self.lets)))
        self.prog.add("io is region\nio in main\nio strategy arena\nio maxBytes 1048576\nio released atReturn")
        for e in self.entities:
            self.prog.add(e)
        printers = {"String": sb.show_text, "Int64": sb.show_int, "Bool": sb.show_bool}
        for typ in sorted(self.shown):
            self.prog.add(printers[typ]())
        self.prog.imports = [f"standard.{m}" for m in sorted(self.imports)]
        return self.prog.render()


def _deadlines(p: Probe) -> tuple[str, str, str]:
    """A deadline five seconds away, one that has passed, and none."""
    p.let("fiveSeconds Int64 5000 immutable")
    p.let("noTime Int64 0 immutable")
    soon = p.step("time.Deadline.after", ["milliseconds Int64 fiveSeconds copy"], out="soon time.Deadline")
    gone = p.step("time.Deadline.after", ["milliseconds Int64 noTime copy"], out="gone time.Deadline")
    never = p.step("time.Deadline.never", [], out="forever time.Deadline")
    return soon, gone, never


def files_probe() -> str:
    p = Probe("nativeFiles")
    p.capability("fileAccess", ['read fs.files "suite-*"', 'write fs.files "suite-*"'])
    soon, gone, _never = _deadlines(p)
    missing = p.let('missing String "suite-missing.txt" immutable')
    plain = p.let('plain String "suite-a.txt" immutable')
    folder = p.let('folder String "suite-d" immutable')
    inner = p.let('inner String "suite-d/f.txt" immutable')
    nothing = p.let('nothing String "suite-nothing" immutable')
    body = p.let('body String "héllo" immutable')
    p.let("small Int64 3 immutable")
    p.let("big Int64 4096 immutable")
    p.let("five Int64 5 immutable")
    p.let("zero Int64 0 immutable")
    p.let("ff Byte 255 immutable")
    p.let('abc String "abc" immutable')
    raw = p.step("string.toBytes", [f"text String {body} lend"], out="bodyBytes Bytes", owned="none", borrows=body)
    p.step("fs.readAll", [f"path String {missing} lend", "region Region io lend", "maxBytes Int64 big copy",
                          f"deadline time.Deadline {soon} copy"], "fs.FileError", "r0 Bytes", "io", task=True)
    p.step("fs.writeAll", [f"path String {plain} lend", f"bytes Bytes {raw} lend",
                           f"deadline time.Deadline {soon} copy"], "fs.FileError", task=True)
    p.step("fs.readAll", [f"path String {plain} lend", "region Region io lend", "maxBytes Int64 small copy",
                          f"deadline time.Deadline {soon} copy"], "fs.FileError", "r1 Bytes", "io", task=True)
    p.step("fs.readAll", [f"path String {plain} lend", "region Region io lend", "maxBytes Int64 big copy",
                          f"deadline time.Deadline {gone} copy"], "fs.FileError", "r2 Bytes", "io", task=True)
    got = p.step("fs.readAll", [f"path String {plain} lend", "region Region io lend", "maxBytes Int64 big copy",
                                f"deadline time.Deadline {soon} copy"], "fs.FileError", "r3 Bytes", "io", task=True,
                 needed=True)
    p.step("string.fromBytes", [f"bytes Bytes {got} lend", "region Region io lend"], "string.Utf8Error",
           "readText String", "io", show="String")
    buf = p.step("buffer.new", ["region Region io lend"], out="buf buffer.ByteBuffer", owned="io")
    p.step("buffer.appendString", [f"buffer buffer.ByteBuffer {buf} lendMutable", "text String abc lend"])
    p.step("buffer.appendInt64", [f"buffer buffer.ByteBuffer {buf} lendMutable", "value Int64 five copy"])
    p.step("buffer.length", [f"buffer buffer.ByteBuffer {buf} lend"], out="bufLength Int64", show="Int64")
    p.step("buffer.toString", [f"buffer buffer.ByteBuffer {buf} lend", "region Region io lend"],
           "string.Utf8Error", "bufText String", "io", show="String")
    p.step("buffer.appendByte", [f"buffer buffer.ByteBuffer {buf} lendMutable", "value Byte ff copy"])
    p.step("buffer.toString", [f"buffer buffer.ByteBuffer {buf} lend", "region Region io lend"],
           "string.Utf8Error", "badText String", "io")
    bad = p.step("buffer.toBytes", [f"buffer buffer.ByteBuffer {buf} lend"], out="badBytes Bytes", borrows=buf)
    p.step("string.fromBytes", [f"bytes Bytes {bad} lend", "region Region io lend"], "string.Utf8Error",
           "badDecoded String", "io")
    p.step("fs.createDirectory", [f"path String {folder} lend"], "fs.FileError")
    p.step("fs.createDirectory", [f"path String {folder} lend"], "fs.FileError")
    p.step("fs.writeAll", [f"path String {inner} lend", f"bytes Bytes {raw} lend",
                           f"deadline time.Deadline {soon} copy"], "fs.FileError", task=True)
    p.step("fs.removeDirectory", [f"path String {folder} lend"], "fs.FileError")
    listing = p.step("fs.listDirectory", [f"path String {folder} lend", "region Region io lend"], "fs.FileError",
                     "listing fs.DirectoryListing", "io")
    p.step("fs.listDirectory", [f"path String {nothing} lend", "region Region io lend"], "fs.FileError",
           "noListing fs.DirectoryListing", "io")
    p.step("fs.writeAll", [f"path String {folder} lend", f"bytes Bytes {raw} lend",
                           f"deadline time.Deadline {soon} copy"], "fs.FileError", task=True)
    p.step("fs.remove", [f"path String {inner} lend"], "fs.FileError")
    p.step("fs.remove", [f"path String {inner} lend"], "fs.FileError")
    p.step("fs.removeDirectory", [f"path String {folder} lend"], "fs.FileError")
    p.step("fs.exists", [f"path String {plain} lend"], out="plainExists Bool", show="Bool")
    p.step("fs.exists", [f"path String {folder} lend"], out="folderExists Bool", show="Bool")
    p.step("fs.removeDirectory", [f"path String {plain} lend"], "fs.FileError")
    return p.render()


def listing_probe() -> str:
    p = Probe("nativeListing")
    p.capability("fileAccess", ['read fs.files "suite-*"', 'write fs.files "suite-*"'])
    soon, _gone, _never = _deadlines(p)
    folder = p.let('folder String "suite-list" immutable')
    names = [p.let(f'name{i} String "suite-list/{n}" immutable') for i, n in enumerate(("b", "a", "é", "B"))]
    body = p.let('body String "x" immutable')
    p.let("five Int64 5 immutable")
    p.let("zero Int64 0 immutable")
    p.let("one Int64 1 immutable")
    p.let("two Int64 2 immutable")
    p.let("three Int64 3 immutable")
    raw = p.step("string.toBytes", [f"text String {body} lend"], out="bodyBytes Bytes", borrows=body)
    p.step("fs.createDirectory", [f"path String {folder} lend"], "fs.FileError")
    for n in names:
        p.step("fs.writeAll", [f"path String {n} lend", f"bytes Bytes {raw} lend",
                               f"deadline time.Deadline {soon} copy"], "fs.FileError", task=True)
    listing = p.step("fs.listDirectory", [f"path String {folder} lend", "region Region io lend"], "fs.FileError",
                     "listing fs.DirectoryListing", "io", needed=True)
    p.step("fs.entryCount", [f"listing fs.DirectoryListing {listing} lend"], out="entries Int64", show="Int64")
    for i, at in enumerate(("zero", "one", "two", "three", "five")):
        p.step("fs.entryName", [f"listing fs.DirectoryListing {listing} lend", f"index Int64 {at} copy",
                                "region Region io lend"], "fs.EntryIndexError", f"entry{i} String", "io",
               show="String")
    return p.render()


def process_probe(program: str | None) -> str:
    p = Probe("nativeProcess")
    p.capability("argumentReader", ["read process.arguments none"])
    p.capability("environmentReader", ["read environment.variables none"])
    p.capability("stdinReader", ["read console.stdin none"])
    p.capability("missingRunner", ['spawn process.programs "semanticscript-no-such-program"'])
    if program:
        p.capability("childRunner", [f'spawn process.programs "{program}"'])
    soon, gone, never = _deadlines(p)
    p.let("zero Int64 0 immutable")
    p.let("nine Int64 9 immutable")
    p.let("three Int64 3 immutable")
    p.let("plenty Int64 4096 immutable")
    p.let('present String "SEMANTICSCRIPT_NATIVE_PROBE" immutable')
    p.let('absent String "SEMANTICSCRIPT_NATIVE_ABSENT" immutable')
    p.let('missingProgram String "semanticscript-no-such-program" immutable')
    p.let('versionFlag String "--version" immutable')
    p.let('hashFlag String "hash-object" immutable')
    p.let('stdinFlag String "--stdin" immutable')
    p.let('feed String "piped input" immutable')
    p.step("process.argumentCount", [], out="argCount Int64", show="Int64")
    p.step("process.argument", ["index Int64 zero copy", "region Region io lend"], "process.ArgumentError",
           "arg0 String", "io", show="String")
    p.step("process.argument", ["index Int64 nine copy", "region Region io lend"], "process.ArgumentError",
           "arg9 String", "io", show="String")
    p.step("environment.get", ["name String present lend", "region Region io lend"], "environment.MissingError",
           "envValue String", "io", show="String")
    p.step("environment.get", ["name String absent lend", "region Region io lend"], "environment.MissingError",
           "envMissing String", "io", show="String")
    for i, (limit, deadline) in enumerate((("three", soon), ("plenty", never), ("plenty", soon), ("plenty", soon))):
        p.step("console.readLine", ["region Region io lend", f"maxBytes Int64 {limit} copy",
                                    f"deadline time.Deadline {deadline} copy"], "console.ReadError",
               f"line{i} String", "io", task=True, show="String")
    noargs = p.step("process.newArguments", ["region Region io lend"], out="noArgs process.Arguments", owned="io")
    p.step("process.run", ["program String missingProgram lend", f"arguments process.Arguments {noargs} lend",
                           f"deadline time.Deadline {soon} copy"], "process.RunError", "missingStatus ExitCode",
           task=True)
    if program:
        version = p.step("process.newArguments", ["region Region io lend"], out="versionArgs process.Arguments",
                         owned="io")
        p.step("process.addArgument", [f"arguments process.Arguments {version} lendMutable",
                                       "text String versionFlag lend"])
        p.step("process.run", [f"program String {p.texts.get(program) or p.text(program)} lend",
                               f"arguments process.Arguments {version} lend", f"deadline time.Deadline {gone} copy"],
               "process.RunError", "lateStatus ExitCode", task=True)
        hashing = p.step("process.newArguments", ["region Region io lend"], out="hashArgs process.Arguments",
                         owned="io")
        p.step("process.addArgument", [f"arguments process.Arguments {hashing} lendMutable",
                                       "text String hashFlag lend"])
        p.step("process.addArgument", [f"arguments process.Arguments {hashing} lendMutable",
                                       "text String stdinFlag lend"])
        fed = p.step("string.toBytes", ["text String feed lend"], out="feedBytes Bytes", borrows="feed")
        for i, limit in enumerate(("plenty", "three")):
            p.step("process.runCaptured", [f"program String {p.texts[program]} lend",
                                           f"arguments process.Arguments {hashing} lend", f"input Bytes {fed} lend",
                                           "region Region io lend", f"maxBytes Int64 {limit} copy",
                                           f"deadline time.Deadline {soon} copy"], "process.RunError",
                   f"captured{i} process.Output", "io", task=True)
    return p.render()


def collections_probe() -> str:
    p = Probe("nativeCollections", ("map", "set"))
    p.prog.add("Names is typeInstance\nNames purpose \"Counts by name\"\nNames instantiates map.Map String Int64")
    p.prog.add("Numbers is typeInstance\nNumbers purpose \"Counts by number\"\nNumbers instantiates map.Map Int64 Int64")
    p.prog.add("Seen is typeInstance\nSeen purpose \"Numbers seen\"\nSeen instantiates set.Set Int64")
    for i, word in enumerate(("alpha", "beta", "gamma", "Alpha")):
        p.let(f'word{i} String "{word}" immutable')
    for i in range(4):
        p.let(f"n{i} Int64 {i * 10 - 5} immutable")
    names = p.step("Names.new", ["region Region io lend"], out="names Names", owned="io")
    numbers = p.step("Numbers.new", ["region Region io lend"], out="numbers Numbers", owned="io")
    seen = p.step("Seen.new", ["region Region io lend"], out="seen Seen", owned="io")
    for i in (0, 1, 2, 3, 0):
        p.step("Names.put", [f"map Names {names} lendMutable", f"key String word{i} lend", f"value Int64 n{i} copy"])
        p.step("Numbers.put", [f"map Numbers {numbers} lendMutable", f"key Int64 n{i} copy",
                               f"value Int64 n{(i + 1) % 4} copy"])
        p.step("Seen.add", [f"set Seen {seen} lendMutable", f"item Int64 n{i} copy"])
    p.step("Names.remove", [f"map Names {names} lendMutable", "key String word1 lend"], "map.KeyMissing")
    p.step("Names.remove", [f"map Names {names} lendMutable", "key String word1 lend"], "map.KeyMissing")
    p.step("Names.put", [f"map Names {names} lendMutable", "key String word1 lend", "value Int64 n3 copy"])
    p.step("Names.length", [f"map Names {names} lend"], out="nameCount Int64", show="Int64")
    for i in range(4):
        p.step("Names.get", [f"map Names {names} lend", f"key String word{i} lend"], "map.KeyMissing",
               f"got{i} Int64", show="Int64")
        p.step("Names.contains", [f"map Names {names} lend", f"key String word{i} lend"], out=f"has{i} Bool",
               show="Bool")
        p.step("Numbers.get", [f"map Numbers {numbers} lend", f"key Int64 n{i} copy"], "map.KeyMissing",
               f"num{i} Int64", show="Int64")
    p.step("Numbers.remove", [f"map Numbers {numbers} lendMutable", "key Int64 n2 copy"], "map.KeyMissing")
    p.step("Numbers.get", [f"map Numbers {numbers} lend", "key Int64 n2 copy"], "map.KeyMissing", "gone Int64",
           show="Int64")
    p.step("Numbers.length", [f"map Numbers {numbers} lend"], out="numberCount Int64", show="Int64")
    p.step("Seen.remove", [f"set Seen {seen} lendMutable", "item Int64 n1 copy"])
    p.step("Seen.remove", [f"set Seen {seen} lendMutable", "item Int64 n1 copy"])
    for i in range(4):
        p.step("Seen.contains", [f"set Seen {seen} lend", f"item Int64 n{i} copy"], out=f"in{i} Bool", show="Bool")
    p.step("Seen.length", [f"set Seen {seen} lend"], out="seenCount Int64", show="Int64")
    return p.render()


def _check_same(jit, exe) -> None:
    assert exe[0] == jit[0], (jit, exe)
    assert exe[1] == jit[1], (jit[1], exe[1])
    assert exe[2] == jit[2], (jit[2], exe[2])
    assert exe[3] == jit[3], (sorted(jit[3]), sorted(exe[3]))


@needs_cc
def test_native_files_match_the_jit(tmp_path):
    """D-80, D-52: file targets in an executable give the same results and the same error variants and payloads
    (`notFound`, `tooLarge`, `timedOut`, `exists`, `failed` with its code, `Utf8Error.invalidAt` with its offset),
    and leave the same files."""
    jit, exe = both(_project(str(tmp_path / "files"), "nativeFiles", files_probe()))
    _check_same(jit, exe)
    assert "c6 tooLarge" in jit[1] and "c7 timedOut" in jit[1] and "c4 notFound" in jit[1], jit[1]
    out = jit[1].replace("\r", "")
    assert "abc5" in out and "c16 invalidAt\n4\n" in out and "c18 invalidAt\n4\n" in out, out
    assert "c22 failed" in out and "c27 notFound" in out and "true\nfalse\n" in out, out


@needs_cc
def test_native_listing_is_sorted_like_the_jit(tmp_path):
    """D-80: a directory listing is sorted by the bytes of its names, and an index past its end is `outOfRange`."""
    jit, exe = both(_project(str(tmp_path / "listing"), "nativeListing", listing_probe()))
    _check_same(jit, exe)
    assert "outOfRange\n5" in jit[1].replace("\r", ""), jit[1]


@needs_cc
def test_native_process_targets_match_the_jit(tmp_path):
    """D-80, D-82, D-83: arguments, environment variables, standard input lines (`tooLong`, `endOfInput`), and child
    processes (`notFound`, a passed deadline is `timedOut`, captured output and `tooLarge`) as under the JIT."""
    program = "git" if shutil.which("git") else None
    project = _project(str(tmp_path / "process"), "nativeProcess", process_probe(program))
    jit, exe = both(project, args=("first word", "second"), stdin="toolong\nok\n",
                    env={"SEMANTICSCRIPT_NATIVE_PROBE": "probe value"})
    _check_same(jit, exe)
    out = jit[1].replace("\r", "")
    assert "2\nfirst word\n" in out and "outOfRange\n9" in out and "probe value" in out, out
    assert "tooLong" in out and "\nok\n" in out and "endOfInput" in out and "notFound" in out, out
    if program:
        assert "timedOut" in out and "tooLarge" in out, out


@needs_cc
def test_native_maps_and_sets_match_the_jit(tmp_path):
    """D-80, D-61: maps with text keys compared by content, plain keys, removal and putting again, and sets."""
    jit, exe = both(_project(str(tmp_path / "collections"), "nativeCollections", collections_probe()))
    _check_same(jit, exe)
    assert "missing" in jit[1], jit[1]


def _chain_program(depth: int) -> str:
    """`main` starts a task that calls through `depth` operations; the last divides by zero."""
    p = sb.Prog("chain", "Trap deep inside a task", imports=["standard.math"])
    for i in range(depth):
        last = i == depth - 1
        steps = [("begin", "do divide" if last else f"do next{i}"), ("begin", "return ok none")]
        p.add(sb.op(f"level{i}", "One level of the chain", steps, lets=("one Int64 1 immutable",
                                                                        "nothing Int64 0 immutable")))
        if last:
            p.add(sb.call("divide", f"level{i}", "math.divideInt64", ("left Int64 one copy", "right Int64 nothing copy"),
                          out="quotient Int64"))
        else:
            p.add(sb.call(f"next{i}", f"level{i}", f"level{i + 1}"))
    p.add(sb.op("main", "Start the chain as a task", [("begin", "start runChain into none"),
                                                      ("begin", "join runChain"), ("begin", "return ok okCode")],
                output="ExitCode", waits=True, lets=("okCode ExitCode 0 immutable",)))
    p.add(sb.call("runChain", "main", "level0", kind="task"))
    return p.render()


@needs_cc
def test_native_traps_print_the_jit_trace(tmp_path):
    """D-85: a trap's trace in an executable is the JIT's: innermost first, at most 12 lines, `... and N more`, the
    task line, a recursion collapsed with its depth past any fixed frame table, and a negative duration trap."""
    jit, exe = both(_project(str(tmp_path / "chain"), "chain", _chain_program(16)))
    _check_same(jit, exe)
    assert re.search(r"[.]{3} and [0-9]+ more", jit[2]) and "(in a task started with `start`)" in jit[2], jit[2]
    deep = os.path.join(caselib.PROGRAMS, "06-recursion", "trap-recursion-depth.sem")
    with open(deep, encoding="utf-8") as fh:
        text = fh.read().replace("descend maxRecursion 10", "descend maxRecursion 100000")
    text = text.replace("main let depth Int64 50 immutable", "main let depth Int64 200000 immutable")
    jit, exe = both(_project(str(tmp_path / "deep"), "deepRecursion", text))
    _check_same(jit, exe)
    assert "(100000 calls deep)" in jit[2], jit[2]
    p = Probe("negativeSleep")
    p.let("minusFive Int64 -5 immutable")
    p.step("time.sleep", ["milliseconds Int64 minusFive copy"], task=True)
    jit, exe = both(_project(str(tmp_path / "sleep"), "negativeSleep", p.render()))
    _check_same(jit, exe)
    assert "`time.sleep` was given -5 milliseconds" in jit[2], jit[2]


@needs_cc
def test_examples_run_as_executables_with_arguments(tmp_path):
    """Roadmap 1 to 3: the lexer, symbols, and warehouse examples build as executables and behave exactly as under
    `refined run`, with command-line arguments: the same output, errors, exit codes, and written files."""
    runs = [("lexer", ("lexer-sample.txt",)), ("lexer", ("lexer-invalid.txt",)), ("lexer", ()),
            ("lexer", ("lexer-missing.txt",)), ("lexer", ("../outside.txt",)), ("symbols", ()), ("warehouse", ())]

    def one(i):
        example, args = runs[i]
        project = str(tmp_path / f"{example}{i}")
        shutil.copytree(os.path.join(EXAMPLES, example), project,
                        ignore=shutil.ignore_patterns(".refined-cache", "*.tokens"))
        return both(project, args=args)

    with ThreadPoolExecutor(4) as pool:
        results = list(pool.map(one, range(len(runs))))
    for (example, args), (jit, exe) in zip(runs, results):
        _check_same(jit, exe)
    codes = [jit[0] for jit, _exe in results]
    assert codes == [0, 3, 2, 4, 70, 0, 0], codes
    assert "lexer-sample.txt.tokens" in results[0][0][3], sorted(results[0][0][3])


def test_native_targets_and_error_numbers_agree_with_the_library():
    """D-80: the C runtime's target table names only library targets, marks the same scoped parameter as host.py,
    and numbers every error variant it raises as library.py orders them."""
    from refined import host
    from refined.library import LIBRARY
    from refined.native import RUNTIME_C, native_targets
    native = native_targets()
    assert native and set(native) <= set(host.HANDLERS), set(native) - set(host.HANDLERS)
    for name, scoped in native.items():
        assert scoped == host.SCOPED.get(name, -1), name
    with open(RUNTIME_C, encoding="utf-8") as fh:
        source = fh.read()
    errors = re.findall(r"#define ERR_(\w+?)_(\w+?)_(\w+) (\d+)", source)
    assert len(errors) >= 20
    for mod, enum, variant, number in errors:
        variants = [v for v, _p in LIBRARY[mod]["types"][enum].variants]
        assert variants.index(variant) + 1 == int(number), (mod, enum, variant)
