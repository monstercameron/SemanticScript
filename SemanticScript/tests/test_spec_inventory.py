"""Spec-conformance gate for the language syntax inventory.

`docs/reference/syntax-inventory.md` is the language's source of truth: a table
of `| syntax | description | status |` rows where status is Impl'd / Partial /
Not impl'd. Nothing previously connected those claims to executable tests, so a
row could be marked Impl'd without anything proving it compiles.

This gate does two things:

1. **Table integrity** - the inventory parses into well-formed rows with a valid
   status in every row. Catches doc drift (a mangled row, an invalid status).

2. **Impl'd-claim backing** - a maintained map from headline language features to
   a feature-test that exercises that feature. Each mapped test must compile to
   IR (`--emit-ir`, no C compiler needed), so the "Impl'd" claim for that feature
   family is backed by a test that would fail under a no-op/broken lowering. This
   is the explicit inventory<->test linkage the doc itself lacks, and encodes the
   "never call a row Impl'd without a test" rule.

The map is intentionally a curated set of headline features (not all 362 rows);
`compiler.feature-corpus` separately compile-gates the whole numbered corpus.

Run from the repo root:
    python -m unittest SemanticScript/tests/test_spec_inventory.py -v
"""

from __future__ import annotations

import re
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from SemanticScript.linter import semlint
from SemanticScript.tools import sem

REPO_ROOT = Path(__file__).resolve().parents[2]
SEMSC = REPO_ROOT / "SemanticScript" / "compiler" / "semsc.py"
INVENTORY = REPO_ROOT / "docs" / "reference" / "syntax-inventory.md"
CORPUS = REPO_ROOT / "SemanticScript" / "sem" / "feature_tests"
SEM = REPO_ROOT / "SemanticScript" / "tools" / "sem.py"
README_EXECUTABLE_DOCS = (
    REPO_ROOT / "README.md",
    REPO_ROOT / "docs" / "getting-started.md",
)

# Status vocabulary actually used by the inventory: implemented, partially
# implemented, proposed-but-unbuilt, and explicitly not implemented.
VALID_STATUS = {"Impl'd", "Partial", "Proposed", "Not impl'd"}

# Headline feature -> a feature-test (known to pass) that exercises it. Each is
# compiled to IR to back the inventory's Impl'd claim for that family. Keep the
# right-hand side pointing at a test that genuinely uses the feature.
CONFORMANCE_MAP = {
    "program entry / exit code": "01_exit_zero",
    "integer arithmetic": "05_add_two_consts",
    "conditional branching": "10_branchif_taken",
    "counted loops": "17_loop_sum_1_to_5",
    "user operations + calls": "18_user_op_wrapper",
    "recursion": "39_recursion_factorial",
    "records (multi-field)": "109_record_two_fields",
    "record float fields": "110_record_float_fields",
    "cross-file imports": "121_cross_file_import",
    "local mutable storage": "130_storage_local_mutable",
    "module mutable storage": "131_storage_module_mutable",
    "module-mutable cross-op": "133_module_mutable_cross_op",
    "defer (reverse order)": "134_defer_reverse_order",
    "useRetry retry loop": "135_use_retry_loop",
    "channel send/receive": "136_channel_send_receive",
    "literal source loader": "137_literal_source_loader",
    "json encode primitive": "153_json_encode_int64_primitive",
    "json decode primitive": "156_json_decode_int64_primitive",
    "c interop (strcmp/pointers)": "117_strcmp_with_pointer_params",
}


def _parse_table() -> list[tuple[str, str, str]]:
    text = INVENTORY.read_text(encoding="utf-8")
    rows: list[tuple[str, str, str]] = []
    in_table = False
    for line in text.splitlines():
        if re.match(r"^\|\s*Syntax\s*\|", line):
            in_table = True
            continue
        if in_table and re.match(r"^\|[\s:-]+\|", line):  # the |---|---|---| sep
            continue
        if in_table:
            if not line.startswith("|"):
                in_table = False
                continue
            cells = sem._split_markdown_table_row(line)
            if len(cells) >= 3:
                rows.append((cells[0], cells[1], cells[-1]))
    return rows


def _first_syntax_form(syntax: str) -> str:
    match = re.search(r"`([^`]+)`", syntax)
    return match.group(1).strip() if match else syntax.strip()


def _first_token(syntax: str) -> str:
    form = _first_syntax_form(syntax)
    return form.split(maxsplit=1)[0] if form else ""


def _is_non_row_inventory_surface(token: str, syntax: str) -> bool:
    if not token:
        return True
    if token in {"true", "false", "yes", "no"}:
        return True
    if token.startswith(('"', "#", "[", "{", "<")):
        return True
    if token[:1].isupper():
        return True
    if "." in token:
        return True
    return "JSON" in syntax or " in build-plan JSON" in syntax


def _skill_source_files() -> list[Path]:
    files: list[Path] = []
    for entry in sem.SKILL_REGISTRY:
        for relative in entry["files"]:
            path = REPO_ROOT / relative
            if path not in files:
                files.append(path)
    return files


def _iter_fenced_blocks(path: Path) -> list[tuple[int, str, str]]:
    blocks: list[tuple[int, str, str]] = []
    in_block = False
    block_start = 0
    language = ""
    lines: list[str] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("```"):
            if in_block:
                blocks.append((block_start, language, "\n".join(lines).strip()))
                in_block = False
                block_start = 0
                language = ""
                lines = []
            else:
                in_block = True
                block_start = line_number
                language = stripped[3:].strip().lower()
                lines = []
            continue
        if in_block:
            lines.append(line)
    return blocks


_STALE_ROW_PATTERNS = (
    re.compile(r"^\s*input\s+(?!operation\b)\w+\s+\w+\s+\w+\b"),
    re.compile(r"^\s*output\s+(?!operation\b)\w+\b"),
    re.compile(r"^\s*set\s+(?:local|module)\b"),
    re.compile(r"^\s*memory\s+\w+\s+noHeapAllocation\b"),
    re.compile(r"^\s*purpose\s+(?!operation\b)\w+\b"),
    re.compile(r"^\s*invariant\s+(?!operation\b)\w+\b"),
    re.compile(
        r"^\s*(?:arg|bindOk|bindError|branchIf|branchIfError|returnOk|returnError|"
        r"returnValue|returnVoid|ignoreOk|ignoreValue|ignoreError|const)\b"
    ),
)


def _looks_like_semanticscript_example(language: str, code: str) -> bool:
    if language in {"semanticscript", "sscript"}:
        return True
    if language != "text" or len(code.splitlines()) < 3:
        return False
    first_tokens = [
        stripped.split(maxsplit=1)[0]
        for stripped in (line.strip() for line in code.splitlines())
        if stripped and not stripped.startswith("#")
    ]
    return bool(first_tokens) and all(token in semlint.KNOWN_AGENT_SCRIPT_VERBS for token in first_tokens[:3])


class TestSpecInventory(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rows = _parse_table()

    def test_inventory_table_is_well_formed(self) -> None:
        self.assertGreater(len(self.rows), 300, "inventory table parsed too few rows")
        for syntax, _desc, status in self.rows:
            with self.subTest(syntax=syntax[:40]):
                self.assertTrue(syntax, "empty syntax cell")
                self.assertIn(status, VALID_STATUS,
                              f"row {syntax[:40]!r} has invalid status {status!r}")

    def test_impld_headline_features_compile(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ss_spec_") as tmp:
            for feature, stem in CONFORMANCE_MAP.items():
                with self.subTest(feature=feature):
                    source = CORPUS / (stem + ".sscript")
                    self.assertTrue(source.exists(), f"missing proof-test {source}")
                    proc = subprocess.run(
                        [sys.executable, str(SEMSC), str(source), "--emit-ir",
                         str(Path(tmp) / (stem + ".ll"))],
                        cwd=REPO_ROOT, capture_output=True, text=True, timeout=120,
                    )
                    self.assertEqual(
                        0, proc.returncode,
                        f"Impl'd feature {feature!r} proof-test {stem} failed to "
                        f"compile:\n{proc.stderr or proc.stdout}",
                    )

    def test_conformance_map_targets_exist(self) -> None:
        for feature, stem in CONFORMANCE_MAP.items():
            with self.subTest(feature=feature):
                self.assertTrue((CORPUS / (stem + ".sscript")).exists(),
                                f"{feature}: proof-test {stem}.sscript missing")

    def test_impld_inventory_row_verbs_are_registered_for_parser_and_linter(self) -> None:
        unknown: list[str] = []
        for syntax, _desc, status in self.rows:
            if status != "Impl'd":
                continue
            token = _first_token(syntax)
            if _is_non_row_inventory_surface(token, syntax):
                continue
            if token not in semlint.KNOWN_AGENT_SCRIPT_VERBS:
                unknown.append(f"{syntax} -> {token}")
        self.assertEqual([], unknown)

    def test_skill_bodies_do_not_use_removed_row_format_examples(self) -> None:
        stale: list[str] = []
        for path in _skill_source_files():
            for start_line, language, code in _iter_fenced_blocks(path):
                if not _looks_like_semanticscript_example(language, code):
                    continue
                for offset, line in enumerate(code.splitlines()):
                    for pattern in _STALE_ROW_PATTERNS:
                        if pattern.search(line):
                            stale.append(f"{path.relative_to(REPO_ROOT)}:{start_line + offset}: {line.strip()}")
        self.assertEqual([], stale)

    def test_readme_getting_started_semanticscript_blocks_check_clean(self) -> None:
        checked_blocks = 0
        with tempfile.TemporaryDirectory(prefix="ss_doc_blocks_") as tmp:
            temp_root = Path(tmp)
            for path in README_EXECUTABLE_DOCS:
                for start_line, language, code in _iter_fenced_blocks(path):
                    if language != "semanticscript":
                        continue
                    checked_blocks += 1
                    source = temp_root / f"{path.stem}_{start_line}.sscript"
                    source.write_text(code + "\n", encoding="utf-8")
                    proc = subprocess.run(
                        [sys.executable, str(SEM), "check", "--json", str(source)],
                        cwd=REPO_ROOT,
                        capture_output=True,
                        text=True,
                        timeout=120,
                    )
                    try:
                        payload = json.loads(proc.stdout or "{}")
                    except json.JSONDecodeError:
                        payload = {}
                    diagnostics = payload.get("diagnostics", [])
                    self.assertEqual(
                        0, proc.returncode,
                        f"{path.relative_to(REPO_ROOT)}:{start_line} failed sem check:\n"
                        f"{proc.stdout}\n{proc.stderr}",
                    )
                    self.assertEqual(
                        [],
                        diagnostics,
                        f"{path.relative_to(REPO_ROOT)}:{start_line} produced diagnostics",
                    )
        self.assertGreater(checked_blocks, 0, "no executable SemanticScript doc blocks were checked")

    def test_agent_contract_mirrors_stay_in_sync(self) -> None:
        agents_text = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")
        claude_text = (REPO_ROOT / "CLAUDE.md").read_text(encoding="utf-8")

        def normalize(text: str) -> str:
            return (
                text
                .replace("`CLAUDE.md` in sync", "`PEER_AGENT_CONTRACT.md` in sync")
                .replace("`AGENTS.md` in sync", "`PEER_AGENT_CONTRACT.md` in sync")
            )

        self.assertEqual(normalize(agents_text), normalize(claude_text))


if __name__ == "__main__":
    unittest.main()
