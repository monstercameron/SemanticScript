import http.client
import socket
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "app" / "todo-web-advanced" / "advanced_todo_web.sscript"
EXE = ROOT / "app" / "todo-web-advanced" / "advanced_todo_web.exe"
HOST = "127.0.0.1"
PORT = 18081


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


def request(path, method="GET", body=None, headers=None):
    connection = http.client.HTTPConnection(HOST, PORT, timeout=2)
    try:
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        payload = response.read().decode("utf-8")
        headers = {key.lower(): value for key, value in response.getheaders()}
        return response.status, payload, headers
    finally:
        connection.close()


def raw_http_request(payload):
    with socket.create_connection((HOST, PORT), timeout=2) as sock:
        sock.sendall(payload)
        try:
            sock.shutdown(socket.SHUT_WR)
        except OSError:
            pass
        chunks = []
        while True:
            data = sock.recv(4096)
            if not data:
                break
            chunks.append(data)
    return b"".join(chunks).decode("iso-8859-1")


def parse_raw_response(raw_response):
    header_text, _, body = raw_response.partition("\r\n\r\n")
    status_line = header_text.splitlines()[0]
    status = int(status_line.split(" ")[1])
    headers = {}
    for line in header_text.splitlines()[1:]:
        if ":" in line:
            key, value = line.split(":", 1)
            headers[key.strip().lower()] = value.strip()
    return status, headers, body


def wait_for_server():
    deadline = time.time() + 8
    last_error = None
    while time.time() < deadline:
        try:
            request("/health")
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


def assert_response(path, expected_status, expected_body, method="GET", body=None, headers=None):
    status, payload, response_headers = request(path, method=method, body=body, headers=headers)
    assert status == expected_status, (method, path, status, payload)
    assert payload == expected_body, (method, path, payload)
    assert response_headers.get("content-type") == "text/plain; charset=utf-8", response_headers
    assert response_headers.get("content-length") == str(len(payload)), response_headers


def assert_raw_response(payload, expected_status, expected_body):
    status, headers, body = parse_raw_response(raw_http_request(payload))
    assert status == expected_status, (status, body)
    assert body == expected_body, body
    assert headers.get("content-type") == "text/plain; charset=utf-8", headers
    assert headers.get("content-length") == str(len(body)), headers


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

        assert_response(
            "/",
            200,
            "advanced todo web\nroutes: /health /todos /todos/1 /debug/method /debug/path /debug/header /debug/query /debug/body\n",
        )
        assert_response("/health", 200, "ok\n")
        status, payload, headers = request("/health")
        assert status == 200, (status, payload)
        assert headers.get("x-sem-middleware") == "ran", headers
        assert_response(
            "/todos",
            200,
            "todos\n1. wire native webserver [done]\n2. read request body at /debug/body [done]\n3. add path params [missing]\n",
        )
        assert_response(
            "/todos",
            201,
            "created todo placeholder; storage api missing\n",
            method="POST",
            body="title=from-test",
        )
        assert_response(
            "/todos",
            201,
            "created todo placeholder; storage api missing\n",
            method="POST",
            body="x" * 12000,
        )
        status, payload, headers = request("/todos", method="OPTIONS")
        assert status == 200, (status, payload)
        assert payload == "allow: GET,POST,OPTIONS\nheader: Allow\n", payload
        assert headers.get("allow") == "GET, POST, OPTIONS", headers
        assert_response("/todos/1", 200, "todo 1: wire native webserver\n")
        assert_response(
            "/todos/1",
            200,
            "updated todo placeholder; storage api missing\n",
            method="PUT",
            body="title=updated",
        )
        assert_response(
            "/todos/1",
            200,
            "updated todo placeholder; storage api missing\n",
            method="PUT",
            body="y" * 12000,
        )
        assert_response(
            "/todos/1",
            200,
            "deleted todo placeholder; storage api missing\n",
            method="DELETE",
        )
        assert_response("/debug/method", 200, "GET")
        assert_response("/debug/path?source=query", 200, "/debug/path")
        assert_response(
            "/debug/header",
            200,
            "header-value",
            headers={"X-Sem-Test": "header-value"},
        )
        assert_response("/debug/query?name=semantic", 200, "semantic")
        assert_response(
            "/debug/body",
            200,
            "title=from-test",
            method="POST",
            body="title=from-test",
        )
        assert_raw_response(
            b"POST /debug/body HTTP/1.1\r\n"
            b"Host: 127.0.0.1\r\n"
            b"Content-Length: 70000\r\n"
            b"\r\n",
            413,
            "payload too large\n",
        )
        assert_response("/debug/method", 404, "not found\n", method="POST")
        assert_response("/debug/body", 404, "not found\n", method="GET")
        assert_response("/todos/999", 404, "not found\n")
        assert_response("/todos/", 404, "not found\n")

        for _index in range(10):
            assert_response("/health", 200, "ok\n")

        assert_raw_response(
            b"get /health HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n",
            200,
            "ok\n",
        )
        assert_raw_response(
            b"this-is-not-http\r\n\r\n",
            400,
            "bad request\n",
        )

        print("advanced todo-web native HTTP thorough edge smoke passed")
    finally:
        stop_server(process)
        process.communicate(timeout=2)


if __name__ == "__main__":
    main()
