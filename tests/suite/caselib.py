"""Load and run the program cases in tests/suite/programs.

A case is either one module file, `<case>.sem` (with an optional
`<case>.test.sem` beside it), or a directory holding its own `build.sem`.
Each case starts with header comments that state what it covers and what
must happen; nothing about a case's expectation lives outside the file.

    # covers: <checklist section number> <checklist item>     (one or more)
    # kind: positive | negative | edge
    # expect: check ok
    # expect: check R301 R405          (these codes, in any order, and no others)
    # expect: run                      (with `# exit:` and `# stdout:` rows)
    # expect: trap <text>              (exit code 70; stderr contains <text>)
    # expect: test pass                (every test in the case passes)
    # expect: test fail <text>         (at least one test fails or traps; output contains <text>)
    # expect: unsupported <text>       (checks clean; the backend refuses with R901 naming <text>)
    # exit: <integer>
    # stdout: <one expected line>      (repeat; `# stdout:` alone is an empty line)
    # stderr: <one expected line>      (repeat; checked only when present)
    # args: <words>                    (the program's arguments, for `run` and `trap`)
    # stdin: <one input line>          (repeat; fed to standard input, each with a line end)
    # requires: <program>              (the case is skipped where this program is not installed)

Programs run with their project directory as the working directory, so a case
that writes files writes them there.

A single-file case is placed in a fresh project: `target console` with entry
`<module>.main` when the module exports `main`, otherwise `target library`.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
COMPILER = os.path.join(ROOT, "semanticscript", "compiler", "refined")
PROGRAMS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "programs")
TRAP_EXIT_CODE = 70

sys.path.insert(0, os.path.join(ROOT, "semanticscript", "compiler"))
from refined import check_path  # noqa: E402


@dataclass
class Case:
    name: str  # path relative to PROGRAMS, without `.sem`
    path: str  # the module file, or the case directory
    covers: list[str] = field(default_factory=list)
    kind: str = ""
    expect: str = ""
    exit_code: int | None = None
    stdout: list[str] | None = None
    stderr: list[str] | None = None
    args: list[str] = field(default_factory=list)
    stdin: str = ""
    requires: list[str] = field(default_factory=list)

    def missing_tools(self) -> list[str]:
        return [r for r in self.requires if shutil.which(r) is None]

    @property
    def mode(self) -> str:
        return self.expect.split()[0] if self.expect else ""

    @property
    def detail(self) -> str:
        return self.expect.split(None, 1)[1] if " " in self.expect else ""


_HEADER = re.compile(r"^# (covers|kind|expect|exit|stdout|stderr|args|stdin|requires):(.*)$")


def _parse_header(text: str, case: Case) -> None:
    for line in text.splitlines():
        if not line.startswith("#"):
            if line.strip():
                break
            continue
        m = _HEADER.match(line)
        if not m:
            continue
        key, value = m.group(1), m.group(2)
        value = value[1:] if value.startswith(" ") else value
        if key == "covers":
            case.covers.append(value.strip())
        elif key == "kind":
            case.kind = value.strip()
        elif key == "expect":
            case.expect = value.strip()
        elif key == "exit":
            case.exit_code = int(value.strip())
        elif key == "stdout":
            case.stdout = (case.stdout or []) + [value]
        elif key == "stderr":
            case.stderr = (case.stderr or []) + [value]
        elif key == "requires":
            case.requires.append(value.strip())
        elif key == "args":
            case.args = value.split()
        elif key == "stdin":
            case.stdin += value + "\n"


def discover() -> list[Case]:
    cases = []
    for dirpath, dirnames, filenames in os.walk(PROGRAMS):
        dirnames.sort()
        if "build.sem" in filenames:
            rel = os.path.relpath(dirpath, PROGRAMS).replace(os.sep, "/")
            case = Case(rel, dirpath)
            with open(os.path.join(dirpath, "build.sem"), encoding="utf-8") as fh:
                _parse_header(fh.read(), case)
            cases.append(case)
            dirnames[:] = []
            continue
        for f in sorted(filenames):
            if not f.endswith(".sem") or f.endswith(".test.sem"):
                continue
            full = os.path.join(dirpath, f)
            rel = os.path.relpath(full, PROGRAMS).replace(os.sep, "/")[:-4]
            case = Case(rel, full)
            with open(full, encoding="utf-8") as fh:
                _parse_header(fh.read(), case)
            cases.append(case)
    return cases


_MODULE = re.compile(r"^(\w+) is module$", re.M)
_PATH = re.compile(r"^(\w+) path ([\w.]+)$", re.M)


def materialize(case: Case, workdir: str) -> str:
    """Copy the case into `workdir` as a project and return the project directory."""
    dst = os.path.join(workdir, os.path.basename(case.name))
    if os.path.isdir(case.path):
        shutil.copytree(case.path, dst)
        return dst
    os.makedirs(dst)
    with open(case.path, encoding="utf-8") as fh:
        text = fh.read()
    name = _MODULE.search(text)
    path = _PATH.search(text)
    module = name.group(1) if name else "broken"
    dotted = path.group(2) if path else module
    target = os.path.join(dst, *dotted.split(".")) + ".sem"
    os.makedirs(os.path.dirname(target), exist_ok=True)
    shutil.copyfile(case.path, target)
    test_file = case.path[:-4] + ".test.sem"
    if os.path.exists(test_file):
        shutil.copyfile(test_file, target[:-4] + ".test.sem")
    console = re.search(rf"^{module} exports main$", text, re.M) is not None
    project = "case" + module[0].upper() + module[1:] if module else "case"
    rows = [f"{project} is project", f'{project} purpose "Run one test-suite case"',
            f"{project} target {'console' if console else 'library'}", f'{project} version "0.1.0"',
            f"{project} language refined-1", f"{project} standardLibrary 1", f"{project} requires none",
            f"{project} module {dotted}",
            f"{project} entry {module + '.main' if console else 'none'}"]
    with open(os.path.join(dst, "build.sem"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(rows) + "\n")
    return dst


def module_file(project_dir: str) -> str:
    """The module file of a single-file case's project (the one `.sem` that is not build.sem or a test file)."""
    found = []
    for root, _dirs, files in os.walk(project_dir):
        for f in files:
            if f.endswith(".sem") and f != "build.sem" and not f.endswith(".test.sem"):
                found.append(os.path.join(root, f))
    assert len(found) == 1, found
    return found[0]


def codes(project_dir: str) -> list[str]:
    return [d.code for d in check_path(project_dir).diagnostics]


def diagnostics(project_dir: str) -> list[str]:
    return [d.format() for d in check_path(project_dir).diagnostics]


def refined(*args: str, timeout: int = 300, cwd: str | None = None, stdin: str = "") -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, COMPILER, *args], capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout, cwd=cwd, input=stdin)


def run_case(case: Case, project: str) -> subprocess.CompletedProcess:
    extra = ["--", *case.args] if case.args else []
    return refined("run", os.path.abspath(project), *extra, cwd=project, stdin=case.stdin)


def evaluate(case: Case, workdir: str) -> list[str]:
    """Return a list of problems; empty means the case behaved as its header says."""
    problems: list[str] = []
    if not case.covers:
        problems.append("no `# covers:` rows")
    if case.kind not in ("positive", "negative", "edge"):
        problems.append(f"`# kind:` is `{case.kind}`, not positive, negative, or edge")
    project = materialize(case, workdir)
    mode, detail = case.mode, case.detail
    found = codes(project)
    if mode == "check":
        if detail == "ok":
            if found:
                problems.append("expected a clean check, got:\n  " + "\n  ".join(diagnostics(project)))
        else:
            want = sorted(detail.split())
            if sorted(set(found)) != sorted(set(want)):
                problems.append(f"expected codes {want}, got {sorted(set(found))}:\n  " +
                                "\n  ".join(diagnostics(project)))
        return problems
    if found:
        return problems + ["expected a clean check before running, got:\n  " + "\n  ".join(diagnostics(project))]
    if mode == "run":
        proc = run_case(case, project)
        if case.exit_code is not None and proc.returncode != case.exit_code:
            problems.append(f"exit code {proc.returncode}, expected {case.exit_code}\n{proc.stdout}{proc.stderr}")
        if case.stdout is not None and proc.stdout.splitlines() != case.stdout:
            problems.append(f"stdout {proc.stdout.splitlines()!r}, expected {case.stdout!r}\n{proc.stderr}")
        if case.stderr is not None and proc.stderr.splitlines() != case.stderr:
            problems.append(f"stderr {proc.stderr.splitlines()!r}, expected {case.stderr!r}")
    elif mode == "trap":
        proc = run_case(case, project)
        if proc.returncode != TRAP_EXIT_CODE or detail not in proc.stderr:
            problems.append(f"expected a trap containing {detail!r}; exit {proc.returncode}\n{proc.stdout}{proc.stderr}")
        if case.stdout is not None and proc.stdout.splitlines() != case.stdout:
            problems.append(f"stdout before the trap {proc.stdout.splitlines()!r}, expected {case.stdout!r}")
    elif mode == "test":
        proc = refined("test", project, "--json")
        try:
            results = json.loads(proc.stdout)["results"]
        except (ValueError, KeyError):
            return problems + [f"test runner output is not JSON:\n{proc.stdout}{proc.stderr}"]
        if not results:
            problems.append("the case has no tests")
        if detail == "pass":
            bad = [r for r in results if r["status"] != "pass"]
            if bad:
                problems.append(f"tests did not pass: {bad}")
        elif detail.startswith("fail"):
            text = detail[4:].strip()
            bad = [r for r in results if r["status"] in ("fail", "trapped")]
            if not bad or text not in json.dumps(bad):
                problems.append(f"expected a failing test mentioning {text!r}, got {results}")
        else:
            problems.append(f"unknown test expectation `{detail}`")
    elif mode == "unsupported":
        proc = refined("run", project)
        if proc.returncode != 1 or "R901" not in proc.stdout or detail not in proc.stdout:
            problems.append(f"expected R901 naming {detail!r}; exit {proc.returncode}\n{proc.stdout}{proc.stderr}")
    else:
        problems.append(f"unknown `# expect:` mode `{mode}`")
    return problems
