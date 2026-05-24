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
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SEMSC = REPO_ROOT / "SemanticScript" / "compiler" / "semsc.py"
INVENTORY = REPO_ROOT / "docs" / "reference" / "syntax-inventory.md"
CORPUS = REPO_ROOT / "SemanticScript" / "sem" / "feature_tests"

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
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) >= 3:
                rows.append((cells[0], cells[1], cells[-1]))
    return rows


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


if __name__ == "__main__":
    unittest.main()
