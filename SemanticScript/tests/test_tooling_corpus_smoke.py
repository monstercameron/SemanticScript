"""Formatter + linter robustness over the real shipped source corpus.

The formatter idempotency test (`test_semfmt.py`) and the linter rule tests
(`test_semlint.py`) work on focused fixtures. This guards the tools against the
*real* corpus they ship alongside - every `std/<module>/main.sem` and every
top-level `sem/*.sscript` / `sem/*.sem` sample:

  - `semlint` must run to completion on each file without crashing (no Python
    traceback, exit code in the normal 0/1/2 band) - it may report findings.
  - `semfmt` must be idempotent on each file: formatting an already-formatted
    copy must not change it (`fmt(fmt(x)) == fmt(x)`).

Both checks are build-free and need no C compiler, so this is a component /
ci-fast gate. Files containing `htmlBody` / `htmlTemplate` are skipped from the
formatter check (semfmt is known to de-indent embedded HTML); none exist in the
current corpus, but the guard keeps the test honest if one is added.

Run from the repo root:
    python -m unittest SemanticScript/tests/test_tooling_corpus_smoke.py -v
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SS = REPO_ROOT / "SemanticScript"
SEMLINT = SS / "linter" / "semlint.py"
SEMFMT = SS / "formatter" / "semfmt.py"


def _corpus() -> list[Path]:
    files = sorted((SS / "std").glob("*/main.sem"))
    files += sorted((SS / "sem").glob("*.sscript"))
    files += sorted((SS / "sem").glob("*.sem"))
    return files


def _has_embedded_html(path: Path) -> bool:
    text = path.read_text(encoding="utf-8", errors="ignore")
    return "htmlBody" in text or "htmlTemplate" in text


class TestToolingCorpusSmoke(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.corpus = _corpus()
        assert cls.corpus, "no corpus sources discovered"

    def test_semlint_runs_without_crashing(self) -> None:
        for path in self.corpus:
            with self.subTest(file=str(path.relative_to(SS))):
                proc = subprocess.run(
                    [sys.executable, str(SEMLINT), str(path), "--summary"],
                    cwd=REPO_ROOT, capture_output=True, text=True, timeout=120,
                )
                combined = proc.stdout + proc.stderr
                self.assertNotIn("Traceback (most recent call last)", combined,
                                 f"semlint crashed on {path}:\n{combined}")
                self.assertIn(proc.returncode, (0, 1, 2),
                              f"semlint odd exit {proc.returncode} on {path}:\n{combined}")

    def test_semfmt_is_idempotent_on_corpus(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ss_fmt_corpus_") as temp_dir:
            work = Path(temp_dir)
            for path in self.corpus:
                if _has_embedded_html(path):
                    continue
                with self.subTest(file=str(path.relative_to(SS))):
                    scratch = work / path.name
                    shutil.copyfile(path, scratch)
                    self._fmt(scratch)
                    once = scratch.read_bytes()
                    self._fmt(scratch)
                    twice = scratch.read_bytes()
                    self.assertEqual(once, twice,
                                     f"semfmt not idempotent on {path}")

    def _fmt(self, path: Path) -> None:
        proc = subprocess.run(
            [sys.executable, str(SEMFMT), str(path)],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=120,
        )
        self.assertNotIn("Traceback (most recent call last)", proc.stdout + proc.stderr,
                         f"semfmt crashed on {path}:\n{proc.stdout}\n{proc.stderr}")


if __name__ == "__main__":
    unittest.main()
