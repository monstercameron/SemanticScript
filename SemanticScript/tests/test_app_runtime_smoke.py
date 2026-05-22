import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SEMSC = REPO_ROOT / "SemanticScript" / "compiler" / "semsc.py"


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
    def test_hello_gui_builds_without_opening_window(self) -> None:
        run_command([
            sys.executable,
            str(SEMSC),
            "app/hello-gui/build.sem",
            "--emit-exe",
            "--quiet",
        ])
        self.assertTrue((REPO_ROOT / "app" / "hello-gui" / "build" / "hello_gui.exe").exists())

    def test_html_console_demo_builds_and_runs(self) -> None:
        run_command([
            sys.executable,
            str(SEMSC),
            "app/html-console-demo/build.sem",
            "--emit-exe",
            "--quiet",
        ])
        result = run_command([
            str(REPO_ROOT / "app" / "html-console-demo" / "build" / "html-console-demo.exe")
        ])
        self.assertIn("<!doctype html>", result.stdout)
        self.assertIn("Todo TUI HTML Console Demo", result.stdout)

    def test_todo_tui_builds_and_exits_with_scripted_escape(self) -> None:
        run_command([
            sys.executable,
            str(SEMSC),
            "app/todo/build.sem",
            "--emit-exe",
            "--quiet",
        ])
        env = os.environ.copy()
        env["SEM_TERMINAL_TEST_KEYS"] = chr(27)
        with tempfile.TemporaryDirectory(prefix="ss_todo_tui_") as temp_dir:
            result = subprocess.run(
                [str(REPO_ROOT / "app" / "todo" / "build" / "todo.exe")],
                cwd=temp_dir,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=10,
            )
            self.assertEqual(0, result.returncode, result.stderr.decode("utf-8", errors="replace"))
            self.assertTrue((Path(temp_dir) / "todos.json").exists())

    def test_kilo_port_builds_and_runs_smoke(self) -> None:
        run_command([
            sys.executable,
            str(SEMSC),
            "app/Kilo_port/build.sem",
            "--emit-exe",
            "--quiet",
        ])
        run_command([
            sys.executable,
            "app/Kilo_port/scripts/test_kilo_port.py",
        ])

    def test_todo_web_native_http_smoke(self) -> None:
        run_command([
            sys.executable,
            "app/todo-web/test_todo_web.py",
        ])

    def test_todo_web_advanced_native_http_smoke(self) -> None:
        run_command([
            sys.executable,
            "app/todo-web-advanced/test_advanced_todo_web.py",
        ])

    def test_http_api_gauntlet_native_http_smoke(self) -> None:
        run_command([
            sys.executable,
            "app/http-api-gauntlet/scripts/test_http_api_gauntlet.py",
        ])

    def test_todo_web_pro_native_http_smoke(self) -> None:
        run_command([
            sys.executable,
            "app/todo-web-pro/scripts/test_todo_web_pro.py",
        ])


if __name__ == "__main__":
    unittest.main()
