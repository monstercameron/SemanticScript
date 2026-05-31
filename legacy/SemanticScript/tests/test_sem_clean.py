"""Tests for `sem clean` — artifact discovery, dry-run, force-remove, the
git-clean passthrough, and the repo-escape guard.

Uses a real temporary git repo with a .gitignore so `git check-ignore`
(the basis of _is_ignored) behaves exactly as in production.
"""

import argparse
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

_TOOLS_DIR = str(Path(__file__).resolve().parents[1] / "tools")
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

import sem  # noqa: E402


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _make_repo(tmp: str) -> Path:
    repo = Path(tmp)
    _git(repo, "init")
    (repo / ".gitignore").write_text("build/\n__pycache__/\n*.ll\n", encoding="utf-8")
    # Ignored artifacts: a clean directory and a clean-suffix file (.ll).
    (repo / "build").mkdir()
    (repo / "build" / "out.exe").write_text("x", encoding="utf-8")
    (repo / "__pycache__").mkdir()
    (repo / "__pycache__" / "m.pyc").write_text("x", encoding="utf-8")
    (repo / "stale.ll").write_text("x", encoding="utf-8")
    # Tracked source that must NEVER be cleaned:
    (repo / "main.sem").write_text("project Keep\n", encoding="utf-8")
    return repo


class TestSemClean(unittest.TestCase):
    def test_collect_finds_ignored_artifacts_only(self) -> None:
        with TemporaryDirectory() as tmp:
            repo = _make_repo(tmp)
            with mock.patch.object(sem, "_repo_root", return_value=repo):
                _root, targets = sem._collect_clean_targets([])
            names = {sem._format_clean_target(t, repo) for t in targets}
            self.assertIn("build/", names)
            self.assertIn("__pycache__/", names)
            self.assertIn("stale.ll", names)
            self.assertNotIn("main.sem", names)

    def test_dry_run_lists_but_keeps_files(self) -> None:
        with TemporaryDirectory() as tmp:
            repo = _make_repo(tmp)
            args = argparse.Namespace(all_ignored=False, force=False, paths=[])
            with mock.patch.object(sem, "_repo_root", return_value=repo):
                rc = sem.command_clean(args)
            self.assertEqual(rc, 0)
            self.assertTrue((repo / "build" / "out.exe").exists())
            self.assertTrue((repo / "stale.ll").exists())

    def test_force_removes_ignored_artifacts(self) -> None:
        with TemporaryDirectory() as tmp:
            repo = _make_repo(tmp)
            args = argparse.Namespace(all_ignored=False, force=True, paths=[])
            with mock.patch.object(sem, "_repo_root", return_value=repo):
                rc = sem.command_clean(args)
            self.assertEqual(rc, 0)
            self.assertFalse((repo / "build").exists())
            self.assertFalse((repo / "__pycache__").exists())
            self.assertFalse((repo / "stale.ll").exists())
            self.assertTrue((repo / "main.sem").exists())  # tracked source survives

    def test_nothing_to_clean_returns_zero(self) -> None:
        with TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _git(repo, "init")
            (repo / "main.sem").write_text("project Keep\n", encoding="utf-8")
            args = argparse.Namespace(all_ignored=False, force=True, paths=[])
            with mock.patch.object(sem, "_repo_root", return_value=repo):
                rc = sem.command_clean(args)
            self.assertEqual(rc, 0)

    def test_all_ignored_delegates_to_git_clean(self) -> None:
        args = argparse.Namespace(all_ignored=True, force=False, paths=["."])
        with mock.patch("subprocess.call", return_value=0) as call_mock:
            rc = sem.command_clean(args)
        self.assertEqual(rc, 0)
        invoked = call_mock.call_args.args[0]
        self.assertEqual(invoked[:3], ["git", "clean", "-Xdn"])  # dry-run mode
        # --force flips to the destructive -Xdf mode.
        args_force = argparse.Namespace(all_ignored=True, force=True, paths=["."])
        with mock.patch("subprocess.call", return_value=0) as call_mock2:
            sem.command_clean(args_force)
        self.assertEqual(call_mock2.call_args.args[0][:3], ["git", "clean", "-Xdf"])

    def test_clean_path_escaping_repo_is_rejected(self) -> None:
        with TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            outside = str(Path(tmp) / "outside")
            with self.assertRaises(ValueError):
                sem._clean_roots([outside], repo)

    def test_remove_target_outside_repo_is_refused(self) -> None:
        with TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            outside = Path(tmp) / "evil.tmp"
            outside.write_text("x", encoding="utf-8")
            with self.assertRaises(ValueError):
                sem._remove_clean_target(outside, repo)
            self.assertTrue(outside.exists())  # not deleted


if __name__ == "__main__":
    unittest.main()
