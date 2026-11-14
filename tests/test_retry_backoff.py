import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "semanticscript", "compiler"))

import semanticscript  # noqa: E402

SEMANTICSCRIPT = os.path.join(ROOT, "semanticscript", "compiler", "semanticscript.py")
EXAMPLES = os.path.join(ROOT, "examples")


def _retry_backoff_source() -> str:
    src = open(os.path.join(EXAMPLES, "retry_bounded.sem"), encoding="utf-8").read()
    return src.replace("retryCall useRetry 3\n", "retryCall useRetry 3\nretryCall retryBackoffMs 1\n")


def test_retry_backoff_ms_lowers_to_platform_sleep_between_attempts():
    program = semanticscript.parse(_retry_backoff_source())

    ir = str(semanticscript.lower_to_llvm(program))

    assert "retryBackoff" in ir
    assert 'declare void @"ss_platform_sleep_ms"(i32 %".1")' in ir
    assert 'call void @"ss_platform_sleep_ms"(i32 1)' in ir


def test_retry_backoff_ms_native_link_plan_uses_platform_time_provider():
    program = semanticscript.parse(_retry_backoff_source())

    assert semanticscript._referenced_runtime_symbols(program) == {
        "ss_ffi_count",
        "ss_platform_sleep_ms",
    }
    assert [lib["name"] for lib in semanticscript._runtime_libs_for(program)] == [
        "ss_platform_time",
    ]
    assert semanticscript._runtime_libs_for(program, include_compiler_provided=False) == []


def test_retry_backoff_ms_runs_with_the_existing_bounded_retry_behavior():
    proc = subprocess.run(
        [sys.executable, SEMANTICSCRIPT, "run", "-"],
        input=_retry_backoff_source(),
        capture_output=True,
        encoding="utf-8",
        text=True,
        timeout=20,
    )

    assert proc.returncode == 0, proc.stderr
    assert "---- 3 passed, 0 failed ----" in proc.stdout
