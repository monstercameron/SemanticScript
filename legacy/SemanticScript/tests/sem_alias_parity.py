"""
sem_alias_parity.py - verify .sem sample equivalents.

This harness checks the .sem siblings for the optional reference parity samples:
  1. every listed .sscript sample has a .sem equivalent
  2. the .sem source uses the 1.0 storage/memory forms instead of legacy
     const/var/memory/set forms
  3. the .sem source contains executable call/run/control-flow code, not only
     declarations or literal output constants
  4. when optional JavaScript oracles are present, the .sem program stdout
     matches its JavaScript oracle
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from compare import JS_DIR, PROGRAMS, run_js, normalize


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SEM_DIR = ROOT / "sem"
COMPILER = ROOT / "compiler" / "semsc.py"

EXTRA_PROGRAMS = [
    # Same observable behavior as hello.js; this sample exists to exercise a
    # user-op helper path that the main compare.py matrix does not include.
    ("hello.js", "hello_via_helper.sscript", "", "normal"),
]

FORBIDDEN_LEGACY_PREFIXES = ("const ", "var ", "memory ")
EXECUTABLE_VERBS = {
    "call",
    "arg",
    "run",
    "start",
    "await",
    "bind",
    "bindOk",
    "bindError",
    "ignoreOk",
    "ignoreValue",
    "makeError",
    "declareFailure",
    "branch",
    "branchIf",
    "branchIfError",
    "returnOk",
    "returnError",
    "returnValue",
    "set",
    "new",
    "fieldSet",
    "fieldGet",
    "recordBuild",
}


def active_lines(path: Path) -> list[str]:
    lines: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        lines.append(stripped)
    return lines


def assert_legit_1_0_source(path: Path) -> list[str]:
    problems: list[str] = []
    lines = active_lines(path)

    if "runtime AgentRuntime 1.0" not in lines:
        problems.append("missing runtime AgentRuntime 1.0")

    for line in lines:
        if line.startswith(FORBIDDEN_LEGACY_PREFIXES):
            problems.append(f"legacy declaration form: {line}")
        if line.startswith("set ") and not line.startswith(
            ("set local ", "set module ", "set sharedState ")
        ):
            problems.append(f"legacy set form: {line}")

    if not any(line.startswith("storage ") for line in lines):
        problems.append("missing storage declarations")

    verbs = [line.split()[0] for line in lines]
    executable_count = sum(1 for verb in verbs if verb in EXECUTABLE_VERBS)
    if "call" not in verbs:
        problems.append("missing executable call rows")
    if "run" not in verbs:
        problems.append("missing executable run rows")
    if executable_count < 4:
        problems.append(
            f"too few executable rows for a program sample: {executable_count}"
        )

    return problems


def run_sem(path: Path) -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, str(COMPILER), str(path), "--run"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    return proc.returncode, proc.stdout


def main() -> int:
    failures = 0
    programs = list(PROGRAMS) + EXTRA_PROGRAMS
    js_oracles_available = Path(JS_DIR).is_dir()

    if not js_oracles_available:
        print(
            "[SKIP] JavaScript reference oracles are not present; "
            "alias parity validation is skipped."
        )
        return 0

    for js_basename, sscript_basename, stdin_input, mode in programs:
        sem_path = SEM_DIR / sscript_basename.replace(".sscript", ".sem")
        if not sem_path.exists():
            print(f"[MISS] {sem_path.name}: no .sem equivalent")
            failures += 1
            continue

        source_problems = assert_legit_1_0_source(sem_path)
        if source_problems:
            print(f"[FAIL] {sem_path.name}: source check failed")
            for problem in source_problems:
                print(f"  - {problem}")
            failures += 1
            continue

        try:
            js_rc, js_out = run_js(js_basename, stdin_input, mode)
        except Exception as exc:
            print(f"[ERR ] {sem_path.name}: failed to run JS oracle: {exc}")
            failures += 1
            continue

        try:
            sem_rc, sem_out = run_sem(sem_path)
        except Exception as exc:
            print(f"[ERR ] {sem_path.name}: failed to run .sem source: {exc}")
            failures += 1
            continue

        js_n = normalize(js_out)
        sem_n = normalize(sem_out)
        out_ok = js_n == sem_n
        rc_ok = (mode == "long") or (js_rc == sem_rc)
        ok = out_ok and rc_ok
        status = "OK  " if ok else "FAIL"
        replay_note = " captured" if "mode capturedOutputReplay" in active_lines(sem_path) else ""
        print(
            f"[{status}] {sem_path.name}: rc js={js_rc} sem={sem_rc}; "
            f"out_equal={out_ok}{replay_note}"
        )
        if not ok:
            failures += 1
            print("  --- JS stdout ---")
            print(js_n)
            print("  --- .sem stdout ---")
            print(sem_n)

    total = len(programs)
    if failures:
        print(f"\n{failures} / {total} failure(s).")
        return 1
    print(f"\nAll {total} .sem sample equivalents match their JS oracles.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
