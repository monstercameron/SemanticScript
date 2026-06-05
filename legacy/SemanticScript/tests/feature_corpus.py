"""
feature_corpus.py - compile-gate for the numbered feature-test corpus.

The 168 `SemanticScript/sem/feature_tests/*.sscript` files are the compiler's
focused regression corpus (one construct per file). Historically nothing in the
test suite ran them, so breakage went unnoticed. This harness compiles every
one to LLVM IR (`--emit-ir`) and checks the outcome against an explicit
expectation:

  - most files MUST compile (rc == 0);
  - a tracked XFAIL set MUST still fail (rc != 0) - these are constructs the
    current `semsc` front end / codegen does not yet support (refined-syntax
    parse gaps and a handful of typed-codegen gaps). Tracking them as XFAIL
    keeps the rot *visible*: if one starts compiling it is reported as an
    XPASS failure so the entry can be removed.

`--emit-ir` exercises parsing + lowering + codegen but needs no C compiler
(no native link), so this is a fast, cross-platform component/ci-fast gate.
Run from the repo root:

    python SemanticScript/tests/feature_corpus.py
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
CORPUS_DIR = ROOT / "sem" / "feature_tests"

# Feature tests the current semsc front end / codegen cannot compile yet, keyed
# by file stem -> short reason. Two clusters:
#   * refined-syntax parse gaps (set memory/storage, start/await sync lowering,
#     useRetry, task groups, worker pools, locks, metadata clusters), and
#   * typed-codegen gaps (i8<->Int64 terminator compares, Float64 operand
#     typing, unresolved handler symbols, high-level json.parse.<Record>,
#     submitWork user-op resolution).
# An XFAIL that starts compiling is reported as an XPASS *failure* so this list
# is pruned rather than left stale.
XFAIL = {
    "74_writeline_with_bind_string": "SSCG002 equalInt64 expects Int64, got i8",
    "77_pointer_typed_var": "SSCG002 equalInt64 expects Int64, got i8",
    "88_string_byte_scan_loop": "SSCG002 equalInt64 expects Int64, got i8",
    "119_signal_handler_register": "SSCG002 unresolved symbol 'myHandler'",
    "123_record_float_field_param": "SSCG002 multiplyFloat64 expects Float64, got i64",
    "128_typed_method_calls": "SSCG002 high-level json.parse.<Record> unsupported",
    "129_concurrency_verbs_compile": "SSCG001 submitWork target not a user operation",
    "132_shared_state_mutable": "parse: refined 'set memory|storage' form",
    "138_start_await_sync_lowering": "parse: refined start/await sync lowering",
    "141_use_retry_exhaustion_counts": "parse: refined useRetry form",
    "142_use_retry_max_attempts_boundary": "parse: refined useRetry form",
    "146_task_group_runs_child": "parse: refined task-group form",
    "147_worker_pool_submit_work_runs": "parse: refined worker-pool form",
    "148_lock_critical_section_state": "parse: refined lock form",
    "160_metadata_cluster_smoke": "parse: refined metadata-cluster form",
}

COMPILE_TIMEOUT = 60


def compile_to_ir(source: Path, out_path: Path) -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, str(SEMSC), str(source), "--emit-ir", str(out_path)],
        capture_output=True,
        text=True,
        timeout=COMPILE_TIMEOUT,
    )
    return proc.returncode, (proc.stderr or proc.stdout)


def main() -> int:
    sources = sorted(CORPUS_DIR.glob("*.sscript"))
    if not sources:
        print(f"[ERR ] no feature tests found under {CORPUS_DIR}")
        return 1

    stems = {s.stem for s in sources}
    stale_xfail = sorted(set(XFAIL) - stems)
    if stale_xfail:
        print(f"[ERR ] XFAIL names not in corpus (rename/delete): {stale_xfail}")
        return 1

    passed = xfailed = 0
    unexpected_fail: list[tuple[str, str]] = []
    unexpected_pass: list[str] = []
    started = time.perf_counter()

    with tempfile.TemporaryDirectory(prefix="ss_feature_corpus_") as temp_dir:
        work = Path(temp_dir)
        for source in sources:
            stem = source.stem
            rc, diag = compile_to_ir(source, work / (stem + ".ll"))
            is_xfail = stem in XFAIL
            if rc == 0 and not is_xfail:
                passed += 1
            elif rc != 0 and is_xfail:
                xfailed += 1
            elif rc != 0 and not is_xfail:
                first = next((ln for ln in diag.splitlines() if ln.strip()), "")
                unexpected_fail.append((stem, first[:100]))
            else:  # rc == 0 and is_xfail -> XPASS
                unexpected_pass.append(stem)

    elapsed = time.perf_counter() - started
    total = len(sources)
    print(
        f"feature corpus: {passed} compiled, {xfailed} xfail, "
        f"{len(unexpected_fail)} unexpected-fail, {len(unexpected_pass)} xpass "
        f"of {total} ({elapsed:.1f}s)."
    )
    for stem, diag in unexpected_fail:
        print(f"[FAIL] {stem}: {diag}")
    for stem in unexpected_pass:
        print(f"[XPASS] {stem}: now compiles; remove from XFAIL in feature_corpus.py")

    if unexpected_fail or unexpected_pass:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
