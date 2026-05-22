from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen


APP_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = APP_ROOT.parents[1]
BACKEND_EXE = REPO_ROOT / "apps" / "taskforge-web" / "build" / "taskforge_web.exe"


def run(args: list[str], timeout: int = 60) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=str(REPO_ROOT),
        text=True,
        capture_output=True,
        timeout=timeout,
        check=True,
    )


def health_ok() -> bool:
    try:
        with urlopen("http://127.0.0.1:18090/health", timeout=2) as response:
            return response.status == 200
    except URLError:
        return False


def wait_for_backend(timeout_seconds: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if health_ok():
            return True
        time.sleep(0.25)
    return False


def start_backend_if_needed() -> subprocess.Popen[str] | None:
    if health_ok():
        return None
    if not BACKEND_EXE.exists():
        run([
            sys.executable,
            "-m",
            "SemanticScript.compiler.semsc",
            "apps/taskforge-web/build.sem",
            "--emit-exe",
            "--quiet",
        ], timeout=90)
    process = subprocess.Popen(
        [str(BACKEND_EXE)],
        cwd=str(REPO_ROOT / "apps" / "taskforge-web"),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    if not wait_for_backend():
        process.terminate()
        raise RuntimeError("TaskForge backend did not become healthy on port 18090")
    return process


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate the TaskForge async SemanticScript client.")
    parser.add_argument(
        "--real-backend",
        action="store_true",
        help="also build the real libuv/libcurl executable and run it against taskforge-web",
    )
    args = parser.parse_args(argv)

    run([
        sys.executable,
        "SemanticScript/linter/semlint.py",
        "apps/taskforge-api-client/main.sem",
        "--summary",
    ])
    run([
        sys.executable,
        "SemanticScript/compiler/semsc.py",
        "apps/taskforge-api-client/main.sem",
        "--emit-ir",
        "--quiet",
    ])
    run([
        sys.executable,
        "-m",
        "SemanticScript.compiler.semsc",
        "apps/taskforge-api-client/build.sem",
        "--lint",
        "--parse-only",
    ])

    if not args.real_backend:
        print("semantic async client source checks passed")
        return 0

    backend = start_backend_if_needed()
    try:
        completed = run([
            sys.executable,
            "apps/taskforge-api-client/scripts/build_async_client.py",
            "--run",
        ], timeout=240)
    finally:
        if backend is not None:
            backend.terminate()
            backend.wait(timeout=10)

    output = completed.stdout + completed.stderr
    required = [
        "started TaskForge fetches before awaiting",
        "TaskForge /health response:",
        "{\"status\":\"ok\",\"app\":\"taskforge-web\"}",
        "TaskForge /api/version response:",
        "\"bcryptCost\":12",
        "TaskForge /api/todos unauthenticated response:",
        "\"code\":\"unauthorized\"",
    ]
    missing = [needle for needle in required if needle not in output]
    if missing:
        raise AssertionError("real async client output missed expected text: " + ", ".join(missing))
    print("real async client run passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
