import http.client
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "app" / "todo-web" / "todo_web.sscript"
EXE = ROOT / "app" / "todo-web" / "todo_web.exe"
HOST = "127.0.0.1"
PORT = 18080


def run_command(args):
    result = subprocess.run(
        args,
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        raise AssertionError(
            "command failed: {}\nstdout:\n{}\nstderr:\n{}".format(
                " ".join(str(arg) for arg in args),
                result.stdout,
                result.stderr,
            )
        )
    return result


def request(path, method="GET"):
    connection = http.client.HTTPConnection(HOST, PORT, timeout=2)
    try:
        connection.request(method, path)
        response = connection.getresponse()
        body = response.read().decode("utf-8")
        headers = {key.lower(): value for key, value in response.getheaders()}
        return response.status, body, headers
    finally:
        connection.close()


def wait_for_server():
    deadline = time.time() + 8
    last_error = None
    while time.time() < deadline:
        try:
            request("/")
            return
        except OSError as exc:
            last_error = exc
            time.sleep(0.1)
    raise AssertionError(f"server did not become reachable: {last_error}")


def stop_server(process):
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=2)


def main():
    run_command([
        sys.executable,
        "SemanticScript/compiler/semsc.py",
        str(SOURCE),
        "--parse-only",
        "--lint",
    ])
    run_command([
        sys.executable,
        "SemanticScript/linter/semlint.py",
        str(SOURCE),
        "--summary",
    ])
    run_command([
        sys.executable,
        "SemanticScript/compiler/semsc.py",
        str(SOURCE),
        "--emit-exe",
        str(EXE),
        "--quiet",
    ])

    process = subprocess.Popen(
        [str(EXE)],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        wait_for_server()

        status, body, headers = request("/")
        assert status == 200, (status, body)
        assert body == "hello from todo web\n", body
        assert headers.get("content-type") == "text/plain; charset=utf-8", headers
        assert headers.get("content-length") == str(len(body)), headers

        status, body, _headers = request("/?sample=1")
        assert status == 200, (status, body)
        assert body == "hello from todo web\n", body

        status, body, headers = request("/missing")
        assert status == 404, (status, body)
        assert body == "not found\n", body
        assert headers.get("content-type") == "text/plain; charset=utf-8", headers

        print("todo-web native HTTP smoke passed")
    finally:
        stop_server(process)
        process.communicate(timeout=2)


if __name__ == "__main__":
    main()
