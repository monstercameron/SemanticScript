"""CLI error-handling contracts for semsc and sem.

The happy paths and strict-mode rejections are covered elsewhere; this locks
the *operator-facing* failure surface that is easy to regress into an ugly
Python traceback: a missing source file, an unknown flag, and a missing/unknown
subcommand. The contract is "fail with a clean diagnostic and a non-zero exit,
never a traceback."

Run from the repo root:
    python -m unittest SemanticScript/tests/test_cli_errors.py -v
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SEMSC = REPO_ROOT / "SemanticScript" / "compiler" / "semsc.py"
SEM = REPO_ROOT / "SemanticScript" / "tools" / "sem.py"
MISSING = "SemanticScript/sem/__does_not_exist__.sscript"


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, *args],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=120,
    )


class TestCliErrors(unittest.TestCase):
    def _assert_clean_failure(self, proc: subprocess.CompletedProcess, *, needle: str = "") -> None:
        combined = proc.stdout + proc.stderr
        self.assertNotEqual(0, proc.returncode, f"expected non-zero exit\n{combined}")
        self.assertNotIn("Traceback (most recent call last)", combined,
                         f"CLI leaked a Python traceback:\n{combined}")
        if needle:
            self.assertIn(needle, combined, f"missing {needle!r} in:\n{combined}")

    def test_semsc_missing_source_file(self) -> None:
        proc = _run(str(SEMSC), MISSING, "--parse-only")
        self._assert_clean_failure(proc, needle="cannot read source file")
        self.assertEqual(2, proc.returncode)

    def test_semsc_unknown_flag(self) -> None:
        proc = _run(str(SEMSC), "SemanticScript/sem/hello.sscript", "--bogus-flag")
        self._assert_clean_failure(proc, needle="usage:")
        self.assertEqual(2, proc.returncode)

    def test_semsc_no_arguments(self) -> None:
        proc = _run(str(SEMSC))
        self._assert_clean_failure(proc)

    def test_sem_check_missing_file(self) -> None:
        proc = _run(str(SEM), "check", "SemanticScript/sem/__does_not_exist__.sem")
        self._assert_clean_failure(proc)

    def test_sem_unknown_subcommand(self) -> None:
        proc = _run(str(SEM), "__bogus_subcommand__")
        self._assert_clean_failure(proc, needle="usage:")
        self.assertEqual(2, proc.returncode)

    def test_semsc_non_utf8_source_is_clean(self) -> None:
        # Regression for the fuzzer-found crash: a non-UTF-8 source must report
        # a clean diagnostic, not raise UnicodeDecodeError out of main().
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad_encoding.sscript"
            path.write_bytes(b"purpose operation main \xff\xfe not utf-8\n")
            proc = _run(str(SEMSC), str(path), "--parse-only")
            self._assert_clean_failure(proc, needle="not valid UTF-8")
            self.assertEqual(2, proc.returncode)

    def test_semsc_unterminated_string_is_clean(self) -> None:
        # Regression for the fuzzer-found crash: an unterminated string literal
        # must surface as a clean parse error, not a SyntaxError traceback that
        # escapes build-tape sniffing.
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "unterminated.sscript"
            path.write_text('purpose operation main "Register\n', encoding="utf-8")
            proc = _run(str(SEMSC), str(path), "--parse-only")
            self._assert_clean_failure(proc)
            self.assertEqual(2, proc.returncode)


if __name__ == "__main__":
    unittest.main()
