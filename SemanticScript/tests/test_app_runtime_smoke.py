import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SEMSC = REPO_ROOT / "SemanticScript" / "compiler" / "semsc.py"
APPS_ROOT = REPO_ROOT / "apps"


def run_command(args: list[str], *, cwd: Path = REPO_ROOT, timeout: int = 300) -> subprocess.CompletedProcess:
    result = subprocess.run(
        args,
        cwd=cwd,
        text=True,
        capture_output=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise AssertionError(
            "command failed: {}\nstdout:\n{}\nstderr:\n{}".format(
                " ".join(args),
                result.stdout,
                result.stderr,
            )
        )
    return result


class TestAppRuntimeSmoke(unittest.TestCase):
    def test_desktop_window_smoke_builds_without_opening_window(self) -> None:
        run_command([
            sys.executable,
            str(SEMSC),
            "apps/desktop-window-smoke/build.sem",
            "--emit-exe",
            "--quiet",
        ])
        self.assertTrue((APPS_ROOT / "desktop-window-smoke" / "build" / "desktop_window_smoke.exe").exists())

    def test_html_template_lab_builds_and_runs(self) -> None:
        run_command([
            sys.executable,
            str(SEMSC),
            "apps/html-template-lab/build.sem",
            "--emit-exe",
            "--quiet",
        ])
        result = run_command([
            str(APPS_ROOT / "html-template-lab" / "build" / "html-template-lab.exe")
        ])
        self.assertIn("<!doctype html>", result.stdout)
        self.assertIn("TaskForge TUI HTML Template Lab", result.stdout)

    def test_taskforge_tui_builds_and_exits_with_scripted_escape(self) -> None:
        run_command([
            sys.executable,
            str(SEMSC),
            "apps/taskforge-tui/build.sem",
            "--emit-exe",
            "--quiet",
        ])
        env = os.environ.copy()
        env["SEM_TERMINAL_TEST_KEYS"] = chr(27)
        with tempfile.TemporaryDirectory(prefix="ss_todo_tui_") as temp_dir:
            result = subprocess.run(
                [str(APPS_ROOT / "taskforge-tui" / "build" / "taskforge_tui.exe")],
                cwd=temp_dir,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=10,
            )
            self.assertEqual(0, result.returncode, result.stderr.decode("utf-8", errors="replace"))
            self.assertTrue((Path(temp_dir) / "todos.json").exists())

    def test_event_stream_smoke_app_uses_async_event_runtime(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ss_event_stream_smoke_") as temp_dir:
            ir_path = Path(temp_dir) / "event_stream_smoke.ll"
            run_command([
                sys.executable,
                str(SEMSC),
                "apps/event-stream-smoke/main.sem",
                "--emit-ir",
                str(ir_path),
                "--quiet",
            ])
            ir_text = ir_path.read_text(encoding="utf-8")
        self.assertIn("ss_event_append", ir_text)
        self.assertIn("ss_event_receive", ir_text)
        self.assertIn("ss_event_append_start", ir_text)
        self.assertIn("ss_event_receive_start", ir_text)
        self.assertIn("ss_event_receive_await", ir_text)
        self.assertIn("ss_async_queue_work", ir_text)
        app_text = (APPS_ROOT / "event-stream-smoke" / "main.sem").read_text(encoding="utf-8")
        self.assertNotIn("run appendSmokeEventCall", app_text)
        self.assertNotIn("run firstReceiveCall", app_text)
        self.assertNotIn("run secondReceiveCall", app_text)
        self.assertLess(app_text.index("start firstReceiveCall"), app_text.index("start appendSmokeEventCall"))
        self.assertLess(app_text.index("start secondReceiveCall"), app_text.index("start appendSmokeEventCall"))

    def test_http_runtime_gauntlet_native_http_smoke(self) -> None:
        run_command([
            sys.executable,
            "apps/http-runtime-gauntlet/scripts/test_http_runtime_gauntlet.py",
        ])

    def test_taskforge_web_native_http_smoke(self) -> None:
        run_command([
            sys.executable,
            "apps/taskforge-web/scripts/test_taskforge_web.py",
        ])


if __name__ == "__main__":
    unittest.main()
