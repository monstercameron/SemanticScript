import re
import subprocess
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SEM = REPO_ROOT / "SemanticScript" / "tools" / "sem.py"
APP_ROOT = REPO_ROOT / "apps"
STD_ROOT = REPO_ROOT / "SemanticScript" / "std"

APP_CHECK_TARGETS = (
    APP_ROOT / "desktop-window-smoke",
    APP_ROOT / "html-template-lab",
    APP_ROOT / "http-runtime-gauntlet",
    APP_ROOT / "taskforge-tui",
    APP_ROOT / "taskforge-web",
)

REPLACED_ROW_RE = re.compile(
    r"^(?:"
    r"importModule|arg|bindOk|bindError|branchIf|branchIfError|"
    r"returnValue|returnOk|returnError|returnVoid|"
    r"ignoreValue|ignoreOk|ignoreError|memoryHeap|"
    r"const|var|let|modulePurpose|moduleInvariant|"
    r"htmlTemplate|htmlArg|htmlBody"
    r")\b"
)
REVERSED_AUTHORITY_RE = re.compile(
    r"^authority\s+\S+\s+[^\s]+\s+"
    r"(?:read|write|append|open|close|allocate|free|observe|log|"
    r"execute|connect|send|receive|delete|configure|create|update|network)\b"
)
BARE_SET_RE = re.compile(r"^set\s+(?!memory\b|storage\b)")
IGNORE_OK_VOID_RE = re.compile(r"^ignore\s+ok\s+source\s+\S+\s+type\s+(?:Void|CVoid)\b")


def semantic_sources(root: Path) -> list[Path]:
    return sorted(
        path for path in root.rglob("*")
        if path.is_file() and path.suffix in {".sem", ".sscript"}
    )


class TestAppSyntaxCutover(unittest.TestCase):
    def test_app_and_std_sources_do_not_use_replaced_rows(self) -> None:
        failures: list[str] = []
        for path in [*semantic_sources(APP_ROOT), *semantic_sources(STD_ROOT)]:
            relative = path.relative_to(REPO_ROOT)
            for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                if (
                    REPLACED_ROW_RE.search(stripped)
                    or REVERSED_AUTHORITY_RE.search(stripped)
                    or BARE_SET_RE.search(stripped)
                    or IGNORE_OK_VOID_RE.search(stripped)
                ):
                    failures.append(f"{relative}:{line_number}: {stripped}")
        self.assertEqual([], failures)

    def test_all_app_targets_parse_and_lint(self) -> None:
        failures: list[str] = []
        for target in APP_CHECK_TARGETS:
            proc = subprocess.run(
                [sys.executable, str(SEM), "check", str(target)],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
            )
            if proc.returncode != 0:
                output = (proc.stdout + proc.stderr).strip()
                failures.append(f"{target.relative_to(REPO_ROOT)} failed with {proc.returncode}\n{output}")
        self.assertEqual([], failures)


if __name__ == "__main__":
    unittest.main()
