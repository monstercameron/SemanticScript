"""Unit tests for the release version-matrix tool.

Covers collect_versions (structure + every component), the _python_assignment
helper (hit and miss), print_table rendering, and main()'s --json, table, and
error-exit paths.
"""

import io
import json
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

_TOOLS_DIR = str(Path(__file__).resolve().parents[1] / "tools")
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

import release_versions  # noqa: E402


class TestCollectVersions(unittest.TestCase):
    def test_payload_shape_and_components(self) -> None:
        payload = release_versions.collect_versions()
        self.assertEqual(payload["schemaVersion"], "sem.releaseVersions.v0")
        self.assertIn("versionPolicy", payload)
        names = {c["name"] for c in payload["components"]}
        # The four command components are always present by name.
        self.assertTrue({"semsc", "semlint", "semfmt", "sem"}.issubset(names))
        # Exactly one vscode-extension component is appended.
        kinds = [c["kind"] for c in payload["components"]]
        self.assertEqual(kinds.count("vscode-extension"), 1)

    def test_every_command_component_has_a_nonempty_version(self) -> None:
        payload = release_versions.collect_versions()
        for component in payload["components"]:
            if component["kind"] == "command":
                self.assertTrue(component["version"], component)
                self.assertIn("versionSource", component)
                self.assertTrue(component["path"].endswith(".py"))


class TestPythonAssignment(unittest.TestCase):
    def test_reads_assignment(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "mod.py"
            path.write_text('__version__ = "1.2.3"\n', encoding="utf-8")
            self.assertEqual(release_versions._python_assignment(path, "__version__"), "1.2.3")

    def test_missing_assignment_raises(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "mod.py"
            path.write_text("# no version here\n", encoding="utf-8")
            with self.assertRaises(RuntimeError):
                release_versions._python_assignment(path, "__version__")

    def test_unreadable_path_raises(self) -> None:
        missing = Path("does") / "not" / "exist.py"
        with self.assertRaises(RuntimeError):
            release_versions._python_assignment(missing, "__version__")


class TestPrintTableAndMain(unittest.TestCase):
    def test_print_table_renders_header_and_rows(self) -> None:
        payload = release_versions.collect_versions()
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            release_versions.print_table(payload)
        out = buffer.getvalue()
        self.assertIn(payload["versionPolicy"], out)
        self.assertIn("component", out)
        self.assertIn("semsc", out)

    def test_main_json_emits_valid_json(self) -> None:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            rc = release_versions.main(["--json"])
        self.assertEqual(rc, 0)
        parsed = json.loads(buffer.getvalue())
        self.assertEqual(parsed["schemaVersion"], "sem.releaseVersions.v0")

    def test_main_table_path(self) -> None:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            rc = release_versions.main([])
        self.assertEqual(rc, 0)
        self.assertIn("component", buffer.getvalue())

    def test_main_reports_collection_failure(self) -> None:
        original = release_versions.collect_versions

        def boom() -> dict:
            raise RuntimeError("synthetic version failure")

        release_versions.collect_versions = boom
        try:
            err = io.StringIO()
            with redirect_stderr(err):
                rc = release_versions.main(["--json"])
            self.assertEqual(rc, 1)
            self.assertIn("synthetic version failure", err.getvalue())
        finally:
            release_versions.collect_versions = original


if __name__ == "__main__":
    unittest.main()
