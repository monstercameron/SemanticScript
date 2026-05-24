"""
golden_e2e.py - end-to-end golden-output tests.

This is the *aspirational* e2e lane: unlike `native_parity.py` (which uses the
JIT as the oracle and so only proves JIT and native agree), this harness checks
each compiled program against a checked-in, human-verified expected output in
`tests/golden/<name>.golden`. The golden files state what the answer *should* be -
factorial → 3628800, the FizzBuzz sequence, the order-summary JSON totals, etc.
- so a regression that corrupts both the JIT and the native path identically is
still caught here.

Each program is compiled to a native executable (`--emit-exe`), run, and its
stdout is compared byte-for-byte (newline-normalized) against the golden file.
A C compiler is required (clang / `zig cc` / `$SEMSC_CLANG`); this lane is
mandated to have one, so a missing compiler fails loudly rather than skipping.

When intentionally changing a program's output, regenerate its golden with:
    python SemanticScript/compiler/semsc.py SemanticScript/sem/<name>.sscript --run > SemanticScript/tests/golden/<name>.golden
and re-verify the new output is actually correct before committing it.

Run from the repo root:
    python SemanticScript/tests/golden_e2e.py
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
GOLDEN_DIR = HERE / "golden"

BUILD_TIMEOUT = 120
RUN_TIMEOUT = 30

# (sscript_basename, stdin). The expected output lives in golden/<name>.golden and
# has been verified correct by inspection (arithmetic checked, JSON totals
# reconciled, FizzBuzz/control-flow sequences confirmed).
PROGRAMS: list[tuple[str, str]] = [
    ("hello", ""),
    ("hello_world", ""),
    ("factorial", ""),
    ("fizzbuzz", ""),
    ("countdown", ""),
    ("sum_of_squares", ""),
    ("simple_calculator", ""),
    ("number_stats", ""),
    ("string_analyzer", ""),
    ("json_order_summary", ""),
    ("inventory_manager", ""),
    ("event_workflow", ""),
    ("async_workflow", ""),
    ("complex_checkout_saga", ""),
    ("file_inventory", ""),
    # JS-semantics demonstrations - precise, non-obvious expected output
    # (IEEE-754 0.1+0.2, NaN!==NaN, var-vs-let closure capture, microtask
    # ordering, lexicographic sort, this-binding) makes these strong oracles.
    ("esoteric_church_encoding", ""),
    ("esoteric_reactive_proxy", ""),
    ("esoteric_self_referential", ""),
    ("esoteric_stack_language", ""),
    ("esoteric_trampoline", ""),
    ("counterintuitive_closure_capture", ""),
    ("counterintuitive_coercion", ""),
    ("counterintuitive_event_loop", ""),
    ("counterintuitive_mutation", ""),
    ("counterintuitive_numbers", ""),
    ("counterintuitive_this_binding", ""),
    ("todos_list", "1\n7\n"),
]


def _normalize(text: str) -> str:
    return text.replace("\r\n", "\n").rstrip("\n")


def build_and_run(source: Path, stdin_input: str, work_dir: Path) -> tuple[int, str]:
    exe_path = work_dir / (source.stem + "_" + source.suffix.lstrip(".") + ".exe")
    build = subprocess.run(
        [sys.executable, str(SEMSC), str(source), "--emit-exe", str(exe_path)],
        capture_output=True, text=True, timeout=BUILD_TIMEOUT,
    )
    if build.returncode != 0 or not exe_path.exists():
        raise RuntimeError(
            f"native build failed (rc={build.returncode})\n"
            f"stdout:\n{build.stdout}\nstderr:\n{build.stderr}"
        )
    run = subprocess.run(
        [str(exe_path)], input=stdin_input,
        capture_output=True, text=True, timeout=RUN_TIMEOUT,
    )
    return run.returncode, run.stdout


def main() -> int:
    # Each program is checked in every source form that exists: the .sscript
    # original and, when present, its canonical .sem twin. Both must compile
    # and produce the same golden output - this is the alias-parity check
    # against an independent oracle that sem_alias_parity.py only does when the
    # (absent) JS corpus is present.
    targets: list[tuple[str, Path, str]] = []
    missing: list[str] = []
    for name, stdin_input in PROGRAMS:
        if not (GOLDEN_DIR / (name + ".golden")).exists():
            missing.append(name + ".golden")
        forms = [SEM_DIR / (name + suffix) for suffix in (".sscript", ".sem")]
        existing = [f for f in forms if f.exists()]
        if not existing:
            missing.append(name + ".{sscript,sem}")
        for source in existing:
            targets.append((name, source, stdin_input))
    if missing:
        print(f"[ERR ] missing source or golden for: {', '.join(missing)}")
        return 1

    failures = 0
    total_elapsed = 0.0
    with tempfile.TemporaryDirectory(prefix="ss_golden_e2e_") as temp_dir:
        work_dir = Path(temp_dir)
        for name, source, stdin_input in targets:
            label = f"{name}{source.suffix}"
            expected = _normalize((GOLDEN_DIR / (name + ".golden")).read_text(encoding="utf-8"))
            started = time.perf_counter()
            try:
                rc, out = build_and_run(source, stdin_input, work_dir)
            except Exception as exc:
                print(f"[ERR ] {label}: {exc}")
                failures += 1
                continue
            elapsed = time.perf_counter() - started
            total_elapsed += elapsed
            actual = _normalize(out)
            if rc == 0 and actual == expected:
                print(f"[OK  ] {label} ({elapsed:.2f}s)")
                continue
            failures += 1
            print(f"[FAIL] {label} ({elapsed:.2f}s): rc={rc}, output != golden")
            exp_lines = expected.splitlines()
            act_lines = actual.splitlines()
            for i in range(max(len(exp_lines), len(act_lines))):
                e = exp_lines[i] if i < len(exp_lines) else "<missing>"
                a = act_lines[i] if i < len(act_lines) else "<missing>"
                if e != a:
                    print(f"    line {i + 1}:\n      expected: {e!r}\n      actual:   {a!r}")

    total = len(targets)
    if failures:
        print(f"\n{failures} / {total} golden mismatch(es) in {total_elapsed:.1f}s.")
        return 1
    print(f"\nAll {total} program forms match their golden output ({total_elapsed:.1f}s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
