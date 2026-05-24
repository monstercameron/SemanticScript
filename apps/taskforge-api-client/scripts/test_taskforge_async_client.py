from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen


APP_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = APP_ROOT.parents[1]
BACKEND_EXE = REPO_ROOT / "apps" / "taskforge-web" / "build" / "taskforge_web.exe"
ASYNC_TEST_BUILD_ROOT = APP_ROOT / "build" / "real_async_test"
IR_ASSERT_PATH = APP_ROOT / "build" / "async_assert" / "main.ll"
GENERIC_IR_ASSERT_PATH = APP_ROOT / "build" / "async_assert" / "generic-main.ll"
GENERIC_SCALAR_IR_ASSERT_PATH = (
    APP_ROOT / "build" / "async_assert" / "generic-scalar-main.ll"
)


def run(args: list[str], timeout: int = 60) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=str(REPO_ROOT),
        text=True,
        capture_output=True,
        timeout=timeout,
        check=True,
    )


def assert_output_order(output: str, labels: list[str], context: str) -> None:
    positions: list[int] = []
    for label in labels:
        try:
            positions.append(output.index(label))
        except ValueError as exc:
            raise AssertionError(f"{context} output missed {label!r}") from exc
    if positions != sorted(positions):
        raise AssertionError(
            f"{context} did not print completions in readiness order "
            f"{labels!r}; output was {output!r}"
        )


def assert_async_ir_shape() -> None:
    IR_ASSERT_PATH.parent.mkdir(parents=True, exist_ok=True)
    run([
        sys.executable,
        "SemanticScript/compiler/semsc.py",
        "apps/taskforge-api-client/main.sem",
        "--emit-ir",
        str(IR_ASSERT_PATH),
        "--quiet",
    ])
    ir_text = IR_ASSERT_PATH.read_text(encoding="utf-8")
    expected_counts = {
        'call i32 @"ss_http_client_fetch_text_request_start"': 3,
        'call i32 @"ss_http_client_fetch_text_await"': 3,
        'call i32 @"ss_http_client_fetch_body_text_copy"': 3,
        'call i32 @"ss_http_client_fetch_is_ready"': 3,
        'call i32 @"ss_async_loop_run_once"': 1,
    }
    for needle, expected in expected_counts.items():
        actual = ir_text.count(needle)
        if actual != expected:
            raise AssertionError(
                f"expected {expected} IR occurrences of {needle}, found {actual}"
            )
    if 'call i32 @"ss_http_client_fetch_text_request_copy"' in ir_text:
        raise AssertionError("IR still contains blocking net.fetchText request-copy calls")

    last_start = max(
        ir_text.index(f'{name}_start_status')
        for name in ("healthFetchCall", "versionFetchCall", "todosFetchCall")
    )
    started_line = ir_text.index("startedLineCall_res")
    wait_set_jump = ir_text.index('br label %"nextTaskForgeFetch_await_check"')
    if not last_start < started_line < wait_set_jump:
        raise AssertionError(
            "IR does not start all fetch futures before local console work and the wait set"
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


class DelayedTaskForgeHandler(BaseHTTPRequestHandler):
    delay_seconds = 1.0
    delay_seconds_by_path = {
        "/health": 1.0,
        "/api/version": 0.2,
        "/api/todos": 0.6,
    }

    def log_message(self, format: str, *args: object) -> None:
        return

    def do_GET(self) -> None:
        time.sleep(self.delay_seconds_by_path.get(self.path, self.delay_seconds))
        if self.path == "/health":
            self._send_json(200, b'{"status":"ok","app":"delayed-taskforge"}')
        elif self.path == "/api/version":
            self._send_json(
                200,
                b'{"name":"delayed-taskforge","version":"test","bcryptCost":12}',
            )
        elif self.path == "/api/todos":
            self._send_json(
                401,
                b'{"error":{"code":"unauthorized","message":"authentication required"}}',
            )
        else:
            self._send_json(404, b'{"error":"not found"}')

    def _send_json(self, status: int, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def write_delayed_source(port: int) -> Path:
    source_root = APP_ROOT / "build" / "async_concurrency"
    source_root.mkdir(parents=True, exist_ok=True)
    source_text = (APP_ROOT / "main.sem").read_text(encoding="utf-8")
    replacements = {
        "http://127.0.0.1:18090/health": f"http://127.0.0.1:{port}/health",
        "http://127.0.0.1:18090/api/version": (
            f"http://127.0.0.1:{port}/api/version"
        ),
        "http://127.0.0.1:18090/api/todos": (
            f"http://127.0.0.1:{port}/api/todos"
        ),
    }
    for old, new in replacements.items():
        source_text = source_text.replace(old, new)
    delayed_source = source_root / "main_delay.sem"
    delayed_source.write_text(source_text, encoding="utf-8")
    return delayed_source


def write_generic_delayed_source(port: int) -> Path:
    source_root = APP_ROOT / "build" / "async_concurrency"
    source_root.mkdir(parents=True, exist_ok=True)
    source_text = f"""project GenericTaskForgeAsyncClient
target console
runtime AgentRuntime 1.0
entry console main

module app.generic_taskforge_async_client
purpose module app.generic_taskforge_async_client "Probe programmable async by starting a user operation that performs blocking fetch work."

import net standard.net

storage module immutable taskForgeHealthUrl Url "http://127.0.0.1:{port}/health"
storage module immutable taskForgeVersionUrl Url "http://127.0.0.1:{port}/api/version"
storage module immutable taskForgeTodosUrl Url "http://127.0.0.1:{port}/api/todos"
storage module immutable timeoutMillis NetworkTimeoutMilliseconds 3000
storage module immutable maxBodyBytes ResponseBodyLimitBytes 1048576
storage module immutable redirectLimit HttpRedirectLimit 5
storage module immutable successfulExitCode ExitCode 0
storage module immutable failedExitCode ExitCode 1
storage module immutable startedText String "started user-operation fetches before awaiting"
storage module immutable healthBodyLabelText String "generic /health response:"
storage module immutable versionBodyLabelText String "generic /api/version response:"
storage module immutable todosBodyLabelText String "generic /api/todos response:"

operation fetchTaskForgeBody
input operation fetchTaskForgeBody url Url
output operation fetchTaskForgeBody HttpClientBodyText
effect fetchTaskForgeBody write network.http.client
memory fetchTaskForgeBody heap yes
async fetchTaskForgeBody no
purpose operation fetchTaskForgeBody "Run one blocking standard.net fetch and return the owned body pointer."

new request HttpGetRequest
fieldSet request url url
fieldSet request policy.timeoutMillis timeoutMillis
fieldSet request policy.maxBodyBytes maxBodyBytes
fieldSet request policy.redirectLimit redirectLimit

call fetchCall net.fetchText
argument fetchCall request HttpGetRequest request
run fetchCall
bind ok response HttpTextResponse fetchCall
fieldGet body HttpClientBodyText response body
return value body

operation main
input operation main console Console
output operation main ExitCode
effect main write network.http.client
effect main write console.stdout
effect main free heap
memory main heap yes
async main yes
purpose operation main "Start three user-operation calls before awaiting any returned body."

label startMain

call healthBodyCall fetchTaskForgeBody
argument healthBodyCall url Url taskForgeHealthUrl
start healthBodyCall

call versionBodyCall fetchTaskForgeBody
argument versionBodyCall url Url taskForgeVersionUrl
start versionBodyCall

call todosBodyCall fetchTaskForgeBody
argument todosBodyCall url Url taskForgeTodosUrl
start todosBodyCall

call startedLineCall console.writeLine
argument startedLineCall console Console console
argument startedLineCall text String startedText
run startedLineCall
ignore void source startedLineCall

label waitNextBody

await nextTaskForgeBody
case healthBodyCall printHealthBody
case versionBodyCall printVersionBody
case todosBodyCall printTodosBody
done allBodiesPrinted

label printHealthBody

bind ok healthBody HttpClientBodyText healthBodyCall

call printHealthLabelCall console.writeLine
argument printHealthLabelCall console Console console
argument printHealthLabelCall text String healthBodyLabelText
run printHealthLabelCall
ignore void source printHealthLabelCall

call printHealthCall console.writeLine
argument printHealthCall console Console console
argument printHealthCall text String healthBody
run printHealthCall
ignore void source printHealthCall

call releaseHealthBodyCall net.freeTextBody
argument releaseHealthBodyCall body HttpClientBodyText healthBody
run releaseHealthBodyCall
ignore void source releaseHealthBodyCall

jump target waitNextBody

label printVersionBody

bind ok versionBody HttpClientBodyText versionBodyCall

call printVersionLabelCall console.writeLine
argument printVersionLabelCall console Console console
argument printVersionLabelCall text String versionBodyLabelText
run printVersionLabelCall
ignore void source printVersionLabelCall

call printVersionCall console.writeLine
argument printVersionCall console Console console
argument printVersionCall text String versionBody
run printVersionCall
ignore void source printVersionCall

call releaseVersionBodyCall net.freeTextBody
argument releaseVersionBodyCall body HttpClientBodyText versionBody
run releaseVersionBodyCall
ignore void source releaseVersionBodyCall

jump target waitNextBody

label printTodosBody

bind ok todosBody HttpClientBodyText todosBodyCall

call printTodosLabelCall console.writeLine
argument printTodosLabelCall console Console console
argument printTodosLabelCall text String todosBodyLabelText
run printTodosLabelCall
ignore void source printTodosLabelCall

call printTodosCall console.writeLine
argument printTodosCall console Console console
argument printTodosCall text String todosBody
run printTodosCall
ignore void source printTodosCall

call releaseTodosBodyCall net.freeTextBody
argument releaseTodosBodyCall body HttpClientBodyText todosBody
run releaseTodosBodyCall
ignore void source releaseTodosBodyCall

jump target waitNextBody

label allBodiesPrinted

return value successfulExitCode

label failed
return value failedExitCode
"""
    generic_source = source_root / "main_generic_delay.sem"
    generic_source.write_text(source_text, encoding="utf-8")
    return generic_source


def assert_generic_async_ir_shape(source_path: Path) -> None:
    run([
        sys.executable,
        "SemanticScript/compiler/semsc.py",
        str(source_path),
        "--emit-ir",
        str(GENERIC_IR_ASSERT_PATH),
        "--quiet",
    ])
    ir_text = GENERIC_IR_ASSERT_PATH.read_text(encoding="utf-8")
    required = [
        'define void @"__sem_async_work_fetchTaskForgeBody"',
        'call i32 @"ss_async_queue_work"',
        'call i32 @"ss_async_future_await"',
        'call i32 @"ss_async_future_is_ready"',
        'call i32 @"ss_async_loop_run_once"',
        'call i32 @"ss_http_client_fetch_text_request_copy"',
    ]
    missing = [needle for needle in required if needle not in ir_text]
    if missing:
        raise AssertionError("generic async IR missed expected lowering: " + ", ".join(missing))
    if 'call i32 @"ss_http_client_fetch_text_request_start"' in ir_text:
        raise AssertionError(
            "generic async IR should queue the user operation, not rely on fetch-specific start"
        )


def write_generic_scalar_source() -> Path:
    source_root = APP_ROOT / "build" / "async_concurrency"
    source_root.mkdir(parents=True, exist_ok=True)
    source_text = """project GenericScalarAsyncClient
target console
runtime AgentRuntime 1.0
entry console main

module app.generic_scalar_async_client
purpose module app.generic_scalar_async_client "Probe programmable async with scalar-returning user operations."

storage module immutable one Int64 1
storage module immutable two Int64 2
storage module immutable three Int64 3
storage module immutable four Int64 4
storage module immutable ten Int64 10
storage module immutable successfulExitCode ExitCode 0
storage module immutable failedExitCode ExitCode 1
storage module immutable scalarOkText String "generic scalar async result ok"

operation addPair
input operation addPair left Int64
input operation addPair right Int64
output operation addPair Int64
memory addPair heap no
async addPair no
purpose operation addPair "Return the arithmetic sum of two integer inputs."
call addCall math.addInt64
argument addCall left Int64 left
argument addCall right Int64 right
run addCall
bind value sum Int64 addCall
return value sum

operation main
input operation main console Console
output operation main ExitCode
effect main write console.stdout
memory main heap no
async main yes
purpose operation main "Start two scalar user operations, await both, combine the results, and print the total."

label startMain

call firstAddCall addPair
argument firstAddCall left Int64 one
argument firstAddCall right Int64 two
start firstAddCall

call secondAddCall addPair
argument secondAddCall left Int64 three
argument secondAddCall right Int64 four
start secondAddCall

await firstAddCall
bind ok firstResult Int64 firstAddCall

await secondAddCall
bind ok secondResult Int64 secondAddCall

call totalCall math.addInt64
argument totalCall left Int64 firstResult
argument totalCall right Int64 secondResult
run totalCall
bind value total Int64 totalCall

call totalOkCall math.equalInt64
argument totalOkCall left Int64 total
argument totalOkCall right Int64 ten
run totalOkCall
bind value totalOk Bool totalOkCall
branch if condition totalOk target scalarResultOk

return value failedExitCode

label scalarResultOk

call writeOkCall console.writeLine
argument writeOkCall console Console console
argument writeOkCall text String scalarOkText
run writeOkCall
ignore void source writeOkCall

return value successfulExitCode
"""
    scalar_source = source_root / "main_generic_scalar.sem"
    scalar_source.write_text(source_text, encoding="utf-8")
    return scalar_source


def assert_generic_scalar_ir_shape(source_path: Path) -> None:
    run([
        sys.executable,
        "SemanticScript/compiler/semsc.py",
        str(source_path),
        "--emit-ir",
        str(GENERIC_SCALAR_IR_ASSERT_PATH),
        "--quiet",
    ])
    ir_text = GENERIC_SCALAR_IR_ASSERT_PATH.read_text(encoding="utf-8")
    expected_counts = {
        'call i32 @"ss_async_queue_work"': 2,
        'call i32 @"ss_async_future_await"': 2,
        'define void @"__sem_async_work_addPair"': 1,
    }
    for needle, expected in expected_counts.items():
        actual = ir_text.count(needle)
        if actual != expected:
            raise AssertionError(
                f"expected {expected} generic scalar IR occurrences of "
                f"{needle}, found {actual}"
            )


def assert_generic_scalar_result() -> None:
    sys.path.insert(0, str(APP_ROOT / "scripts"))
    import build_async_client

    scalar_source = write_generic_scalar_source()
    assert_generic_scalar_ir_shape(scalar_source)
    exe = build_async_client.build_real_client(
        ASYNC_TEST_BUILD_ROOT,
        "Release",
        scalar_source,
    )
    completed = subprocess.run(
        [str(exe)],
        cwd=str(REPO_ROOT),
        text=True,
        capture_output=True,
        timeout=20,
        check=True,
    )
    output = completed.stdout + completed.stderr
    if "generic scalar async result ok" not in output:
        raise AssertionError(
            "generic scalar async result did not hit the expected success path; "
            f"output was {output!r}"
        )


def manual_timer_demo_exe_path(cmake_build_dir: Path) -> Path:
    executable_names = [
        "sem_async_manual_timer_order_demo.exe",
        "sem_async_manual_timer_order_demo",
    ]
    for executable_name in executable_names:
        matches = list(cmake_build_dir.rglob(executable_name))
        if matches:
            return matches[0]
    raise AssertionError(
        "sem_async_manual_timer_order_demo executable was not produced under "
        f"{cmake_build_dir}"
    )


def assert_manual_timer_promise_order() -> str:
    sys.path.insert(0, str(APP_ROOT / "scripts"))
    import build_async_client

    cmake = shutil.which("cmake")
    if not cmake:
        raise AssertionError("could not find cmake on PATH")

    cmake_build_dir = ASYNC_TEST_BUILD_ROOT / "cmake-build"
    if not (cmake_build_dir / "CMakeCache.txt").exists():
        build_async_client.build_real_client(
            ASYNC_TEST_BUILD_ROOT,
            "Release",
            write_generic_scalar_source(),
        )

    run([
        cmake,
        "--build",
        str(cmake_build_dir),
        "--config",
        "Release",
        "--target",
        "sem_async_manual_timer_order_demo",
    ], timeout=240)

    exe = manual_timer_demo_exe_path(cmake_build_dir)
    completed = subprocess.run(
        [str(exe)],
        cwd=str(REPO_ROOT),
        text=True,
        capture_output=True,
        timeout=20,
        check=True,
    )
    output = completed.stdout + completed.stderr
    required = [
        "resolved B after 20ms",
        "resolved C after 50ms",
        "resolved A after 90ms",
        "manual timer completion order: B,C,A",
    ]
    missing = [needle for needle in required if needle not in output]
    if missing:
        raise AssertionError(
            "manual timer promise demo missed expected output: "
            + ", ".join(missing)
            + f"; output was {output!r}"
        )
    positions = [output.index(needle) for needle in required]
    if positions != sorted(positions):
        raise AssertionError(
            "manual timer promise demo did not print completions in B,C,A order; "
            f"output was {output!r}"
        )
    return "B,C,A"


def assert_real_async_overlap(runs: int) -> list[float]:
    sys.path.insert(0, str(APP_ROOT / "scripts"))
    import build_async_client

    server = ThreadingHTTPServer(("127.0.0.1", 0), DelayedTaskForgeHandler)
    port = server.server_address[1]
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    try:
        delayed_source = write_delayed_source(port)
        exe = build_async_client.build_real_client(
            ASYNC_TEST_BUILD_ROOT,
            "Release",
            delayed_source,
        )
        elapsed_runs: list[float] = []
        for _ in range(runs):
            started = time.perf_counter()
            completed = subprocess.run(
                [str(exe)],
                cwd=str(REPO_ROOT),
                text=True,
                capture_output=True,
                timeout=20,
                check=True,
            )
            elapsed = time.perf_counter() - started
            elapsed_runs.append(elapsed)
            output = completed.stdout + completed.stderr
            for needle in (
                "started TaskForge fetches before awaiting",
                "delayed-taskforge",
                '"code":"unauthorized"',
            ):
                if needle not in output:
                    raise AssertionError(f"delayed async client output missed {needle!r}")
            assert_output_order(
                output,
                [
                    "TaskForge /api/version response:",
                    "TaskForge /api/todos unauthenticated response:",
                    "TaskForge /health response:",
                ],
                "delayed async client",
            )
        slowest = max(elapsed_runs)
        if slowest >= 1.5:
            formatted = ", ".join(f"{value:.3f}s" for value in elapsed_runs)
            raise AssertionError(
                "expected 1.0s, 0.6s, and 0.2s delayed endpoints to overlap; "
                f"runs were {formatted}"
            )
        return elapsed_runs
    finally:
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=5)


def assert_generic_user_op_overlap(runs: int) -> list[float]:
    sys.path.insert(0, str(APP_ROOT / "scripts"))
    import build_async_client

    server = ThreadingHTTPServer(("127.0.0.1", 0), DelayedTaskForgeHandler)
    port = server.server_address[1]
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    try:
        generic_source = write_generic_delayed_source(port)
        assert_generic_async_ir_shape(generic_source)
        exe = build_async_client.build_real_client(
            ASYNC_TEST_BUILD_ROOT,
            "Release",
            generic_source,
        )
        elapsed_runs: list[float] = []
        for _ in range(runs):
            started = time.perf_counter()
            completed = subprocess.run(
                [str(exe)],
                cwd=str(REPO_ROOT),
                text=True,
                capture_output=True,
                timeout=20,
                check=True,
            )
            elapsed_runs.append(time.perf_counter() - started)
            output = completed.stdout + completed.stderr
            for needle in (
                "started user-operation fetches before awaiting",
                "delayed-taskforge",
                '"code":"unauthorized"',
            ):
                if needle not in output:
                    raise AssertionError(
                        f"generic async client output missed {needle!r}"
                    )
            assert_output_order(
                output,
                [
                    "generic /api/version response:",
                    "generic /api/todos response:",
                    "generic /health response:",
                ],
                "generic async client",
            )
        slowest = max(elapsed_runs)
        if slowest >= 1.5:
            formatted = ", ".join(f"{value:.3f}s" for value in elapsed_runs)
            raise AssertionError(
                "expected 1.0s, 0.6s, and 0.2s user-operation fetches to overlap; "
                f"runs were {formatted}"
            )
        return elapsed_runs
    finally:
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=5)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate the TaskForge async SemanticScript client."
    )
    parser.add_argument(
        "--real-backend",
        action="store_true",
        help="also build the real libuv/libcurl executable and run it against taskforge-web",
    )
    parser.add_argument(
        "--concurrency-runs",
        type=int,
        default=3,
        help="number of delayed-server overlap runs for the real libuv/libcurl executable",
    )
    args = parser.parse_args(argv)

    run([
        sys.executable,
        "SemanticScript/linter/semlint.py",
        "apps/taskforge-api-client/main.sem",
        "--summary",
    ])
    assert_async_ir_shape()
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

    overlap_runs = assert_real_async_overlap(max(1, args.concurrency_runs))
    generic_overlap_runs = assert_generic_user_op_overlap(max(1, args.concurrency_runs))
    assert_generic_scalar_result()
    manual_timer_order = assert_manual_timer_promise_order()

    backend = start_backend_if_needed()
    try:
        completed = run([
            sys.executable,
            "apps/taskforge-api-client/scripts/build_async_client.py",
            "--build-root",
            str(ASYNC_TEST_BUILD_ROOT),
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
    formatted_runs = ", ".join(f"{value:.3f}s" for value in overlap_runs)
    print(f"real async overlap benchmark passed: {formatted_runs}")
    formatted_generic_runs = ", ".join(f"{value:.3f}s" for value in generic_overlap_runs)
    print(f"generic user-operation async benchmark passed: {formatted_generic_runs}")
    print("generic scalar user-operation async result passed")
    print(f"manual timer promise order demo passed: {manual_timer_order}")
    print("real async client run passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
