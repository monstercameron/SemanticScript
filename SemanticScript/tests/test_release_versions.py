"""Unit tests for shared SemanticScript version tooling."""

from __future__ import annotations

import io
import json
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

_SEMANTICSCRIPT_DIR = str(Path(__file__).resolve().parents[1])
_TOOLS_DIR = str(Path(__file__).resolve().parents[1] / "tools")
for _path in (_SEMANTICSCRIPT_DIR, _TOOLS_DIR):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from shared import repo_version  # noqa: E402
import bump_version  # noqa: E402
import release_versions  # noqa: E402


def _write_version_file(path: Path, version: str) -> None:
    path.write_text(
        json.dumps({"schemaVersion": "sem.repoVersion.v1", "version": version}, indent=2) + "\n",
        encoding="utf-8",
    )


def _write_package_file(path: Path, version: str) -> None:
    path.write_text(
        json.dumps(
            {
                "name": "semanticscript-vscode",
                "version": version,
                "publisher": "semanticscript-local",
                "license": "MIT",
            },
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )


class TestRepoVersionHelpers(unittest.TestCase):
    def test_read_repo_version_is_valid_semver(self) -> None:
        version = repo_version.read_repo_version()
        self.assertRegex(version, r"^\d+\.\d+\.\d+$")
        self.assertEqual(repo_version.format_semver(*repo_version.parse_semver(version)), version)

    def test_bump_patch_increments_only_patch_segment(self) -> None:
        self.assertEqual(repo_version.bump_patch("0.0.1"), "0.0.2")
        self.assertEqual(repo_version.bump_patch("1.9.9"), "1.9.10")

    def test_write_repo_version_round_trips(self) -> None:
        with TemporaryDirectory() as tmp:
            version_path = Path(tmp) / "version.json"
            repo_version.write_repo_version("0.4.2", version_path)
            self.assertEqual(repo_version.read_repo_version(version_path), "0.4.2")
            payload = repo_version.read_version_payload(version_path)
            self.assertEqual(payload["schemaVersion"], "sem.repoVersion.v1")


class TestBumpVersion(unittest.TestCase):
    def test_apply_version_updates_version_and_package_files(self) -> None:
        with TemporaryDirectory() as tmp:
            version_path = Path(tmp) / "version.json"
            package_path = Path(tmp) / "package.json"
            _write_version_file(version_path, "0.0.1")
            _write_package_file(package_path, "0.0.1")
            payload = bump_version.apply_version("0.0.2", version_path=version_path, package_path=package_path)
            self.assertEqual(payload["previousVersion"], "0.0.1")
            self.assertEqual(repo_version.read_repo_version(version_path), "0.0.2")
            self.assertEqual(bump_version.read_package_version(package_path), "0.0.2")

    def test_check_sync_reports_drift(self) -> None:
        with TemporaryDirectory() as tmp:
            version_path = Path(tmp) / "version.json"
            package_path = Path(tmp) / "package.json"
            _write_version_file(version_path, "0.0.1")
            _write_package_file(package_path, "0.0.3")
            payload = bump_version.check_sync(version_path=version_path, package_path=package_path)
            self.assertFalse(payload["ok"])
            self.assertEqual(payload["version"], "0.0.1")
            self.assertEqual(payload["packageVersion"], "0.0.3")

    def test_main_bump_patch_and_check_paths(self) -> None:
        with TemporaryDirectory() as tmp:
            version_path = Path(tmp) / "version.json"
            package_path = Path(tmp) / "package.json"
            _write_version_file(version_path, "0.0.1")
            _write_package_file(package_path, "0.0.1")
            original_version_file = bump_version.VERSION_FILE
            original_package_json = bump_version.PACKAGE_JSON
            try:
                bump_version.VERSION_FILE = version_path
                bump_version.PACKAGE_JSON = package_path
                stdout = io.StringIO()
                with redirect_stdout(stdout):
                    rc = bump_version.main(["--bump-patch"])
                self.assertEqual(rc, 0)
                self.assertEqual(stdout.getvalue().strip(), "0.0.2")

                stdout = io.StringIO()
                with redirect_stdout(stdout):
                    rc = bump_version.main(["--check", "--json"])
                self.assertEqual(rc, 0)
                payload = json.loads(stdout.getvalue())
                self.assertTrue(payload["ok"])
                self.assertEqual(payload["version"], "0.0.2")
            finally:
                bump_version.VERSION_FILE = original_version_file
                bump_version.PACKAGE_JSON = original_package_json


class TestReleaseVersions(unittest.TestCase):
    def test_payload_shape_and_components(self) -> None:
        payload = release_versions.collect_versions()
        self.assertEqual(payload["schemaVersion"], "sem.releaseVersions.v1")
        self.assertIn("versionPolicy", payload)
        self.assertEqual(payload["repoVersion"], repo_version.read_repo_version())
        names = {c["name"] for c in payload["components"]}
        self.assertTrue({"semsc", "semlint", "semfmt", "sem", "semanticscript-vscode"}.issubset(names))

    def test_every_component_uses_repo_version(self) -> None:
        payload = release_versions.collect_versions()
        for component in payload["components"]:
            self.assertEqual(component["version"], payload["repoVersion"], component)
            self.assertIn("versionSource", component)

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
        self.assertEqual(parsed["schemaVersion"], "sem.releaseVersions.v1")

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
