import http.client
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path


# This test lives in apps/http-runtime-gauntlet/scripts/, so parents[3] is the
# repository root: scripts -> http-runtime-gauntlet -> apps -> repo-root.
ROOT = Path(__file__).resolve().parents[3]
# The gauntlet is compiled via its project-mode build tape (build.sem) per the
# new SYNTAX.md build-tape rows (buildProject / registerModule / mainFile /
# importModule …). build.sem inlines main.sem as the module source; passing
# build.sem to semsc applies the project metadata (VERSIONINFO embedded into
# the PE), the build settings (profile / runtime-checks / native output), and
# the module registry in one compilation unit.
SOURCE = ROOT / "apps" / "http-runtime-gauntlet" / "build.sem"
MODULE_SOURCE = ROOT / "apps" / "http-runtime-gauntlet" / "main.sem"
HOST = "127.0.0.1"
PORT = 18082


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
        response_headers = {key.lower(): value for key, value in response.getheaders()}
        return response.status, payload, response_headers
    finally:
        connection.close()


def request_bytes(path, method="GET", body=None, headers=None):
    connection = http.client.HTTPConnection(HOST, PORT, timeout=2)
    try:
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        payload = response.read()
        response_headers = {key.lower(): value for key, value in response.getheaders()}
        return response.status, payload, response_headers
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


def wait_for_server(process):
    deadline = time.time() + 8
    last_error = None
    while time.time() < deadline:
        if process.poll() is not None:
            stdout, stderr = process.communicate(timeout=2)
            raise AssertionError(
                f"server exited early with {process.returncode}\nstdout:\n{stdout}\nstderr:\n{stderr}"
            )
        try:
            status, payload, headers = request("/health")
            if (
                status == 200
                and payload == "ok\n"
                and headers.get("x-gauntlet-app") == "http-runtime-gauntlet"
            ):
                return
            last_error = AssertionError((status, payload, headers))
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


def assert_common_headers(headers, path):
    assert headers.get("x-gauntlet-middleware") == "active", headers
    assert headers.get("x-gauntlet-path") == path, headers
    assert headers.get("x-gauntlet-app") == "http-runtime-gauntlet", headers
    assert headers.get("x-gauntlet-version") == "1", headers


def assert_response(
    path,
    expected_status,
    expected_body,
    method="GET",
    body=None,
    headers=None,
    expected_content_type="text/plain; charset=utf-8",
    common_path=None,
):
    status, payload, response_headers = request(
        path,
        method=method,
        body=body,
        headers=headers,
    )
    assert status == expected_status, (method, path, status, payload, response_headers)
    assert payload == expected_body, (method, path, payload)
    assert response_headers.get("content-type") == expected_content_type, response_headers
    assert response_headers.get("content-length") == str(len(payload)), response_headers
    if common_path is not None:
        assert_common_headers(response_headers, common_path)
    return response_headers


def assert_response_bytes(
    path,
    expected_status,
    expected_body,
    method="GET",
    body=None,
    headers=None,
    expected_content_type="application/octet-stream",
    common_path=None,
):
    status, payload, response_headers = request_bytes(
        path,
        method=method,
        body=body,
        headers=headers,
    )
    assert status == expected_status, (method, path, status, payload, response_headers)
    assert payload == expected_body, (method, path, payload)
    assert response_headers.get("content-type") == expected_content_type, response_headers
    assert response_headers.get("content-length") == str(len(payload)), response_headers
    if common_path is not None:
        assert_common_headers(response_headers, common_path)
    return response_headers


def assert_raw_response(payload, expected_status, expected_body):
    status, headers, body = parse_raw_response(raw_http_request(payload))
    assert status == expected_status, (status, body, headers)
    assert body == expected_body, body
    assert headers.get("content-length") == str(len(body)), headers
    return headers


def multipart_payload():
    boundary = "SsGauntletBoundary42"
    upload_bytes = b"file-bytes-\x00-end"
    body = (
        b"--" + boundary.encode("ascii") + b"\r\n"
        b"Content-Disposition: form-data; name=\"description\"\r\n"
        b"\r\n"
        b"semantic upload\r\n"
        b"--" + boundary.encode("ascii") + b"\r\n"
        b"Content-Disposition: form-data; name=\"upload\"; filename=\"todo.bin\"\r\n"
        b"Content-Type: application/x-gauntlet\r\n"
        b"\r\n" +
        upload_bytes +
        b"\r\n"
        b"--" + boundary.encode("ascii") + b"--\r\n"
    )
    headers = {"Content-Type": f"multipart/form-data; boundary=\"{boundary}\""}
    return body, headers, upload_bytes


def main():
    with tempfile.TemporaryDirectory(prefix="ss_http_gauntlet_") as temp_dir:
        exe_path = Path(temp_dir) / "http_runtime_gauntlet.exe"

        # Parse + lint via the build tape so project metadata and module
        # registration are validated together with the inlined source.
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
        # Lint the module file standalone too so module-level rules
        # (SS2506 exportedSymbolNotDeclared, the SS36xx webserver-discipline
        # family, etc.) see the full module context, not just the build-tape
        # rows. build.sem linting alone reads the project-level surface;
        # this second pass exercises the in-module contract.
        run_command([
            sys.executable,
            "SemanticScript/linter/semlint.py",
            str(MODULE_SOURCE),
            "--summary",
        ])
        run_command([
            sys.executable,
            "SemanticScript/compiler/semsc.py",
            str(SOURCE),
            "--emit-exe",
            str(exe_path),
            "--quiet",
        ])

        process = subprocess.Popen(
            [str(exe_path)],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            wait_for_server(process)

            index_headers = assert_response(
                "/",
                200,
                "http api gauntlet\nroutes: /health /reflect/method /reflect/path /reflect/header /reflect/required-header-or-fail /reflect/query /reflect/query-empty /reflect/query-repeat /reflect/body /reflect/body-bytes /reflect/body-size /multipart/text /multipart/file-name /multipart/file-type /multipart/file-bytes /events/one /capabilities /content/custom /redirect /empty /patch /middleware-short-circuit\nmissing-input routes respond 400; /reflect/required-header-or-fail intentionally still 500s on missing X-Gauntlet-Required; /middleware-short-circuit returns 418 from its middleware (the route's handler is intentionally skipped by the MiddlewareControl short-circuit contract)\n",
                common_path="/",
            )
            assert index_headers.get("connection") == "close", index_headers
            assert_response("/health", 200, "ok\n", common_path="/health")
            assert_response("/reflect/method", 200, "GET", common_path="/reflect/method")
            assert_response("/reflect/path?debug=true", 200, "/reflect/path", common_path="/reflect/path")

            assert_response(
                "/reflect/header",
                200,
                "token-123",
                headers={"X-Gauntlet-Token": "token-123"},
                common_path="/reflect/header",
            )
            # The source reads lowercase `x-gauntlet-token`; this mixed-case
            # request header pins case-insensitive native header lookup.
            # /reflect/header now guards with pointer.isNull and returns 400 on
            # missing X-Gauntlet-Token (pinned by semlint SS3603). The legacy
            # null-body 500 contract still lives on /reflect/required-header-or-fail
            # below — that's the one route whose `warning` line opts out of the
            # SS3603 lint and keeps the gauntlet's coverage of the adapter's
            # `handler failed` 500 path.
            header_missing_response = assert_response(
                "/reflect/header",
                400,
                "missing header: X-Gauntlet-Token\n",
                common_path="/reflect/header",
            )
            assert header_missing_response.get("x-gauntlet-app") == "http-runtime-gauntlet", header_missing_response
            assert_response(
                "/reflect/required-header-or-fail",
                200,
                "required-yes",
                headers={"X-Gauntlet-Required": "required-yes"},
                common_path="/reflect/required-header-or-fail",
            )
            required_missing_headers = assert_response(
                "/reflect/required-header-or-fail",
                500,
                "handler failed\n",
                common_path="/reflect/required-header-or-fail",
            )
            assert required_missing_headers.get("x-gauntlet-app") == "http-runtime-gauntlet", required_missing_headers

            assert_response(
                "/reflect/query?name=semantic%20script",
                200,
                "semantic%20script",
                common_path="/reflect/query",
            )
            assert_response("/reflect/query-empty?empty", 200, "", common_path="/reflect/query-empty")
            assert_response(
                "/reflect/query-repeat?name=first&name=second",
                200,
                "first",
                common_path="/reflect/query-repeat",
            )

            assert_response(
                "/reflect/body",
                201,
                "semantic-body-123",
                method="POST",
                body="semantic-body-123",
                common_path="/reflect/body",
            )
            assert_response(
                "/reflect/body",
                201,
                "",
                method="POST",
                body="",
                common_path="/reflect/body",
            )
            assert_response_bytes(
                "/reflect/body-bytes",
                200,
                b"abc\x00xyz",
                method="POST",
                body=b"abc\x00xyz",
                common_path="/reflect/body-bytes",
            )
            assert_response(
                "/reflect/body-size",
                200,
                "small body\n",
                method="POST",
                body="small",
                common_path="/reflect/body-size",
            )
            assert_response(
                "/reflect/body-size",
                200,
                "large body\n",
                method="PUT",
                body="0123456789abcdef",
                common_path="/reflect/body-size",
            )

            multipart_body, multipart_headers, upload_bytes = multipart_payload()
            assert_response(
                "/multipart/text",
                200,
                "semantic upload",
                method="POST",
                body=multipart_body,
                headers=multipart_headers,
                common_path="/multipart/text",
            )
            assert_response(
                "/multipart/file-name",
                200,
                "todo.bin",
                method="POST",
                body=multipart_body,
                headers=multipart_headers,
                common_path="/multipart/file-name",
            )
            assert_response(
                "/multipart/file-type",
                200,
                "application/x-gauntlet",
                method="POST",
                body=multipart_body,
                headers=multipart_headers,
                common_path="/multipart/file-type",
            )
            assert_response_bytes(
                "/multipart/file-bytes",
                200,
                upload_bytes,
                method="POST",
                body=multipart_body,
                headers=multipart_headers,
                expected_content_type="application/x-gauntlet",
                common_path="/multipart/file-bytes",
            )

            sse_headers = assert_response(
                "/events/one",
                200,
                "event: gauntlet\ndata: connected\n\n",
                expected_content_type="text/event-stream; charset=utf-8",
                common_path="/events/one",
            )
            assert sse_headers.get("cache-control") == "no-cache", sse_headers

            options_headers = assert_response(
                "/capabilities",
                200,
                "capabilities: method path header query body bodyBytes bodyLength multipart responseHeader responseBytes sse middleware\n",
                method="OPTIONS",
                common_path="/capabilities",
            )
            assert options_headers.get("allow") == "GET, POST, PUT, PATCH, DELETE, OPTIONS", options_headers
            assert options_headers.get("x-gauntlet-methods") == "GET POST PUT PATCH DELETE OPTIONS", options_headers

            assert_response(
                "/content/custom",
                200,
                "custom content\n",
                expected_content_type="application/x-gauntlet; charset=utf-8",
                common_path="/content/custom",
            )

            redirect_headers = assert_response(
                "/redirect",
                302,
                "redirecting\n",
                common_path="/redirect",
            )
            assert redirect_headers.get("location") == "/health", redirect_headers

            assert_response("/empty", 204, "", method="DELETE", common_path="/empty")
            assert_response("/patch", 200, "patched\n", method="PATCH", common_path="/patch")

            # MiddlewareControl short-circuit contract: the dispatcher
            # honours `shortCircuitMiddlewareControl` by skipping the
            # route handler. We expect the middleware-written body
            # (status 418, "middleware short-circuited…") and NOT the
            # handler-written body ("handler ran…"). If the handler
            # body ever shows up here, the dispatcher regressed.
            short_circuit_status, short_circuit_payload, short_circuit_headers = request(
                "/middleware-short-circuit"
            )
            assert short_circuit_status == 418, (
                short_circuit_status, short_circuit_payload, short_circuit_headers
            )
            assert short_circuit_payload == "middleware short-circuited; handler skipped by dispatcher\n", (
                short_circuit_payload, short_circuit_headers
            )
            assert "handler ran" not in short_circuit_payload, (
                "MiddlewareControl short-circuit regression: dispatcher invoked the route "
                "handler even though middleware returned shortCircuitMiddlewareControl. "
                "Payload was: " + short_circuit_payload
            )

            assert_response("/reflect/method", 404, "not found\n", method="POST")
            assert_response("/missing", 404, "not found\n")
            assert_response("/reflect/path/", 404, "not found\n")

            # Negative-path coverage for the new pointer.isNull guards
            # introduced by the SS3603 refactor. Each of these would have
            # returned a 500 ("handler failed\n") before the refine; the
            # refine deliberately exchanged that for a 400 with a static
            # reason body. /reflect/required-header-or-fail is the one
            # route that intentionally keeps the legacy 500 contract
            # (asserted above at lines 273-279 via required_missing_headers).
            assert_response(
                "/reflect/query",
                400,
                "missing query parameter: name\n",
                common_path="/reflect/query",
            )
            assert_response(
                "/reflect/query-empty",
                400,
                "missing query parameter: empty\n",
                common_path="/reflect/query-empty",
            )
            assert_response(
                "/reflect/query-repeat",
                400,
                "missing query parameter: name\n",
                common_path="/reflect/query-repeat",
            )
            assert_response(
                "/multipart/text",
                400,
                "missing multipart field: description\n",
                method="POST",
                body=b"--noBoundary--\r\n",
                headers={"Content-Type": "multipart/form-data; boundary=\"noBoundary\""},
                common_path="/multipart/text",
            )
            assert_response(
                "/multipart/file-name",
                400,
                "missing multipart field: upload (filename)\n",
                method="POST",
                body=b"--noBoundary--\r\n",
                headers={"Content-Type": "multipart/form-data; boundary=\"noBoundary\""},
                common_path="/multipart/file-name",
            )
            assert_response(
                "/multipart/file-type",
                400,
                "missing multipart field: upload (content-type)\n",
                method="POST",
                body=b"--noBoundary--\r\n",
                headers={"Content-Type": "multipart/form-data; boundary=\"noBoundary\""},
                common_path="/multipart/file-type",
            )
            assert_response(
                "/multipart/file-bytes",
                400,
                "missing multipart field: upload (bytes)\n",
                method="POST",
                body=b"--noBoundary--\r\n",
                headers={"Content-Type": "multipart/form-data; boundary=\"noBoundary\""},
                common_path="/multipart/file-bytes",
            )

            lower_method_headers = assert_raw_response(
                b"get /reflect/method HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n",
                200,
                "get",
            )
            assert lower_method_headers.get("x-gauntlet-path") == "/reflect/method", lower_method_headers

            assert_raw_response(
                b"post /reflect/body HTTP/1.1\r\n"
                b"Host: 127.0.0.1\r\n"
                b"Content-Length: 5\r\n"
                b"\r\n"
                b"hello",
                201,
                "hello",
            )
            assert_raw_response(
                b"POST /reflect/body HTTP/1.1\r\n"
                b"Host: 127.0.0.1\r\n"
                b"Content-Length: 70000\r\n"
                b"\r\n",
                413,
                "payload too large\n",
            )
            assert_raw_response(
                b"this-is-not-http\r\n\r\n",
                400,
                "bad request\n",
            )

            for _index in range(20):
                assert_response("/health", 200, "ok\n", common_path="/health")

            print("http api gauntlet native HTTP stress passed")
        finally:
            stop_server(process)
            process.communicate(timeout=2)


if __name__ == "__main__":
    main()
