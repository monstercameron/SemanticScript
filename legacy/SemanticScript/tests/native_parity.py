"""
native_parity.py - end-to-end JIT-vs-native parity harness.

This is the project's self-contained end-to-end check. For each curated sample
program it:
  1. compiles + JIT-runs the program (`semsc --run`) and captures stdout/exit
  2. compiles the same program to a native executable (`semsc --emit-exe`),
     runs the binary, and captures stdout/exit
  3. asserts the two paths agree byte-for-byte (stdout) and on exit code

Unlike the historical `compare.py` / `sem_alias_parity.py` oracles, this needs
no external JavaScript reference corpus: the JIT interpreter is the oracle for
the native backend, so the full lowering -> object -> link -> execute pipeline
is validated end-to-end against a known-good in-process execution of the very
same source. That makes it a true e2e lane that cannot silently no-op: if a C
compiler is unreachable the native builds fail loudly rather than skipping.

Two corpora are exercised the same way:
  - curated deterministic *sample programs* under `sem/`, and
  - every JIT-runnable *stdlib self-test* (`std/<module>/main.test.sem`), so
    each standard-library module gets a true native build+run lane (the four
    native-runtime modules - log/bcrypt/jwt/net - are e2e-covered separately by
    test_native_stdlib_smoke.py, and http is quarantined, so they are excluded
    here and the stdlib list is derived from test_stdlib.OK_MODULES to stay in
    lockstep automatically).

A C compiler is required (clang, or `zig cc`, or `$SEMSC_CLANG`); the e2e /
ci-release lanes mandate one. Run from the repo root:

    python SemanticScript/tests/native_parity.py
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SEMSC = ROOT / "compiler" / "semsc.py"
SEM_DIR = ROOT / "sem"
STD_ROOT = ROOT / "std"

BUILD_TIMEOUT = 120
RUN_TIMEOUT = 30

# (sscript_basename, stdin_input) -- deterministic samples whose stdout is a
# pure function of source + stdin (no clocks, randomness, ports, or network).
# Kept in lockstep with the deterministic rows compare.py used to validate.
PROGRAMS: list[tuple[str, str]] = [
    ("hello.sscript", ""),
    ("hello_world.sscript", ""),
    ("countdown.sscript", ""),
    ("fizzbuzz.sscript", ""),
    ("factorial.sscript", ""),
    ("sum_of_squares.sscript", ""),
    ("simple_calculator.sscript", ""),
    ("number_stats.sscript", ""),
    ("string_analyzer.sscript", ""),
    ("json_order_summary.sscript", ""),
    ("inventory_manager.sscript", ""),
    ("event_workflow.sscript", ""),
    ("async_workflow.sscript", ""),
    ("complex_checkout_saga.sscript", ""),
    ("esoteric_church_encoding.sscript", ""),
    ("esoteric_reactive_proxy.sscript", ""),
    ("esoteric_self_referential.sscript", ""),
    ("esoteric_stack_language.sscript", ""),
    ("esoteric_trampoline.sscript", ""),
    ("counterintuitive_closure_capture.sscript", ""),
    ("counterintuitive_coercion.sscript", ""),
    ("counterintuitive_event_loop.sscript", ""),
    ("counterintuitive_mutation.sscript", ""),
    ("counterintuitive_numbers.sscript", ""),
    ("counterintuitive_this_binding.sscript", ""),
    ("file_inventory.sscript", ""),
    ("todos_list.sscript", "1\n7\n"),
]


def stdlib_targets() -> list[tuple[str, str]]:
    """JIT-runnable stdlib self-tests, as (relative_label, stdin) pairs.

    Derived from test_stdlib.OK_MODULES (+ stdio) so a new module wired into
    the JIT smoke is automatically picked up here too. The native-runtime
    modules (log/bcrypt/jwt/net) and quarantined http are intentionally absent
    from OK_MODULES and so are excluded.
    """
    from test_stdlib import OK_MODULES  # sibling module (tests/ is on sys.path)

    modules = list(OK_MODULES) + ["stdio"]
    return [(f"std/{module}/main.test.sem", "") for module in modules]


def _normalize(text: str) -> str:
    return text.replace("\r\n", "\n").rstrip("\n")


def run_jit(source: Path, stdin_input: str) -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, str(SEMSC), str(source), "--run"],
        input=stdin_input,
        capture_output=True,
        text=True,
        timeout=RUN_TIMEOUT,
    )
    return proc.returncode, proc.stdout


def run_native(source: Path, stdin_input: str, work_dir: Path, stem: str) -> tuple[int, str]:
    exe_path = work_dir / (stem + ".exe")
    build = subprocess.run(
        [sys.executable, str(SEMSC), str(source), "--emit-exe", str(exe_path)],
        capture_output=True,
        text=True,
        timeout=BUILD_TIMEOUT,
    )
    if build.returncode != 0 or not exe_path.exists():
        raise RuntimeError(
            f"native build failed (rc={build.returncode})\n"
            f"stdout:\n{build.stdout}\nstderr:\n{build.stderr}"
        )
    run = subprocess.run(
        [str(exe_path)],
        input=stdin_input,
        capture_output=True,
        text=True,
        timeout=RUN_TIMEOUT,
    )
    return run.returncode, run.stdout


def _resolve(label: str) -> Path:
    # Sample programs are bare basenames under sem/; stdlib labels are paths
    # relative to the SemanticScript root (std/<module>/main.test.sem).
    return (ROOT / label) if "/" in label else (SEM_DIR / label)


def main() -> int:
    targets = [(name, stdin) for name, stdin in PROGRAMS] + stdlib_targets()

    missing = [label for label, _ in targets if not _resolve(label).exists()]
    if missing:
        print(f"[ERR ] missing sources: {', '.join(missing)}")
        return 1

    failures = 0
    total_elapsed = 0.0
    with tempfile.TemporaryDirectory(prefix="ss_native_parity_") as temp_dir:
        work_dir = Path(temp_dir)
        for name, stdin_input in targets:
            source = _resolve(name)
            started = time.perf_counter()
            stem = name.replace("/", "_").replace(".", "_")
            try:
                jit_rc, jit_out = run_jit(source, stdin_input)
                nat_rc, nat_out = run_native(source, stdin_input, work_dir, stem)
            except Exception as exc:  # build/run failure is a hard failure
                print(f"[ERR ] {name}: {exc}")
                failures += 1
                continue
            elapsed = time.perf_counter() - started
            total_elapsed += elapsed
            jit_n, nat_n = _normalize(jit_out), _normalize(nat_out)
            out_ok = jit_n == nat_n
            rc_ok = jit_rc == nat_rc
            if out_ok and rc_ok:
                print(f"[OK  ] {name} ({elapsed:.2f}s): rc={jit_rc}")
                continue
            failures += 1
            print(f"[FAIL] {name} ({elapsed:.2f}s): rc jit={jit_rc} native={nat_rc}; "
                  f"out_equal={out_ok}")
            if not out_ok:
                print("  --- JIT stdout ---")
                print(jit_n)
                print("  --- native stdout ---")
                print(nat_n)

    total = len(targets)
    if failures:
        print(f"\n{failures} / {total} parity failure(s) in {total_elapsed:.1f}s.")
        return 1
    print(f"\nAll {total} programs/modules match JIT<->native ({total_elapsed:.1f}s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
