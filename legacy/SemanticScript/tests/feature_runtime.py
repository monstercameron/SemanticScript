"""
feature_runtime.py - runtime-output gate for the feature corpus.

Every `feature_tests/*.sscript` declares its own oracle in header comments:

    # expect.stdout: 3\n2\n1\n
    # expect.exit: 0

`compiler.feature-corpus` only checks that these compile; this harness *runs*
each compilable test and asserts its actual stdout and exit code match the
declared expectation. That turns ~150 compile-only checks into full
semantic-correctness checks, and because the corpus deliberately includes edge
cases (negative results, zero, modulo, integer/float boundaries, float
classification, non-zero/negative exit codes, pointer and record access), this
doubles as the language's semantic edge-case matrix.

Tests are built to native executables (`--emit-exe`) because several rely on
native runtime adapters (c.printf/snprintf, json primitives) that the JIT
cannot execute. A C compiler is therefore required, so this is an integration /
ci-release gate. The 15 front-end XFAILs from feature_corpus are skipped here
(they do not compile yet); if one starts compiling, feature_corpus flags it.

Run from the repo root:
    python SemanticScript/tests/feature_runtime.py
"""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SEMSC = ROOT / "compiler" / "semsc.py"
CORPUS = ROOT / "sem" / "feature_tests"

BUILD_TIMEOUT = 120
RUN_TIMEOUT = 30

# Front-end gaps shared with feature_corpus.py: these do not compile yet, so
# there is nothing to run. feature_corpus.py owns the XFAIL/XPASS bookkeeping.
XFAIL = {
    "74_writeline_with_bind_string", "77_pointer_typed_var",
    "88_string_byte_scan_loop", "119_signal_handler_register",
    "123_record_float_field_param", "128_typed_method_calls",
    "129_concurrency_verbs_compile", "132_shared_state_mutable",
    "138_start_await_sync_lowering", "141_use_retry_exhaustion_counts",
    "142_use_retry_max_attempts_boundary", "146_task_group_runs_child",
    "147_worker_pool_submit_work_runs", "148_lock_critical_section_state",
    "160_metadata_cluster_smoke",
}

# Tests that compile but whose runtime output does not (yet) match their
# declared oracle. Tracked rather than hidden: a matching entry here is an XPASS
# failure so the entry gets removed once fixed. Most are real semantic bugs this
# gate surfaced; two are non-portable test annotations.
#   real bugs (semantics): 55/71 error payload not propagated to exit code
#   (hardcoded 1); 115 const-name scoping collision (7,7 not 7,42); 122 record
#   typed param reads 0 not the field (cf. XFAIL 123); 139 deferRunOn error-path
#   filter does not fire.
#   non-portable annotations: 102 fpclassify integer constants are libc-specific
#   (glibc 4/2 vs this toolchain -1/0); 92 c.fopen opens a path relative to cwd
#   and the test runs from a temp dir.
KNOWN_DISCREPANCIES = {
    "55_returnerror_payload": "error makeError payload not propagated to exit code (got 1)",
    "71_error_with_distinct_exit_codes": "error payload not propagated to exit code (got 1)",
    "115_const_name_scoping": "per-op const name scoping collision (second op resolves first)",
    "122_record_typed_param": "record-typed param reads 0 instead of field value",
    "139_defer_run_on_filter": "deferRunOn error-path filter does not fire the cleanup",
    "102_fpclassify_const": "fpclassify integer constants are libc-specific (non-portable annotation)",
    "92_c_fopen_fclose": "c.fopen uses a cwd-relative path; test assumes its own dir as cwd",
}


def _unescape(raw: str) -> str:
    # Annotations use C-style \n / \t escapes for readability.
    return raw.replace("\\n", "\n").replace("\\t", "\t")


def read_expectations(path: Path) -> tuple[str | None, int | None]:
    expected_stdout: str | None = None
    expected_exit: int | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"#\s*expect\.stdout:(.*)$", line)
        if m is not None:
            # Strip exactly one leading space after the colon, then unescape.
            value = m.group(1)
            if value.startswith(" "):
                value = value[1:]
            expected_stdout = _unescape(value)
        m = re.match(r"#\s*expect\.exit:\s*(-?\d+)\s*$", line)
        if m is not None:
            expected_exit = int(m.group(1))
    return expected_stdout, expected_exit


def build_and_run(source: Path, work_dir: Path) -> tuple[int, str]:
    exe = work_dir / (source.stem + ".exe")
    build = subprocess.run(
        [sys.executable, str(SEMSC), str(source), "--emit-exe", str(exe)],
        capture_output=True, text=True, timeout=BUILD_TIMEOUT,
    )
    if build.returncode != 0 or not exe.exists():
        raise RuntimeError(f"build failed rc={build.returncode}: {build.stderr[:200]}")
    run = subprocess.run([str(exe)], capture_output=True, text=True, timeout=RUN_TIMEOUT)
    return run.returncode, run.stdout.replace("\r\n", "\n")


def main() -> int:
    sources = sorted(CORPUS.glob("*.sscript"))
    failures: list[str] = []      # unexpected mismatches (real regressions)
    xpasses: list[str] = []       # known-discrepancy that now matches -> prune it
    passed = known = 0
    ran = 0
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="ss_feature_runtime_") as temp_dir:
        work = Path(temp_dir)
        for source in sources:
            stem = source.stem
            if stem in XFAIL:
                continue
            expected_stdout, expected_exit = read_expectations(source)
            if expected_stdout is None and expected_exit is None:
                continue
            ran += 1
            try:
                rc, out = build_and_run(source, work)
            except Exception as exc:
                if stem in KNOWN_DISCREPANCIES:
                    known += 1
                    continue
                failures.append(f"[ERR ] {stem}: {exc}")
                continue
            # Compare with trailing-newline tolerance on both sides.
            got = out.rstrip("\n")
            want = (expected_stdout or "").rstrip("\n")
            ok = got == want and (expected_exit is None or rc == expected_exit)
            if stem in KNOWN_DISCREPANCIES:
                if ok:
                    xpasses.append(stem)
                else:
                    known += 1
                continue
            if ok:
                passed += 1
                continue
            detail = []
            if got != want:
                detail.append(f"stdout exp={want!r} got={got!r}")
            if expected_exit is not None and rc != expected_exit:
                detail.append(f"exit exp={expected_exit} got={rc}")
            failures.append(f"[FAIL] {stem}: " + "; ".join(detail))

    elapsed = time.perf_counter() - started
    print(f"feature runtime: ran {ran} -> {passed} match, {known} known-discrepancy, "
          f"{len(failures)} unexpected, {len(xpasses)} xpass ({elapsed:.1f}s)")
    for line in failures[:40]:
        print("  " + line)
    for stem in xpasses:
        print(f"  [XPASS] {stem}: now matches its oracle; remove from KNOWN_DISCREPANCIES")
    return 1 if (failures or xpasses) else 0


if __name__ == "__main__":
    raise SystemExit(main())
