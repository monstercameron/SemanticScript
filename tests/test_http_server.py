#!/usr/bin/env python3
"""HTTP server integration test (WS3-017). Starts http_server_demo.sem (which
binds a real socket and blocks serving via the SemanticScript HTTP runtime),
probes it with an HTTP client, asserts the response, and tears it down.

This is a separate integration test, not a run_examples harness example, because
the server blocks until signalled. Exit 0 iff the server served the expected body.
"""
import os
import socket
import subprocess
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))          # tests/
ROOT = os.path.dirname(HERE)                               # repo root
SEMANTICSCRIPT = os.path.join(ROOT, "semanticscript", "compiler", "semanticscript.py")
SERVER = os.path.join(ROOT, "examples", "demos", "http_server_demo.sem")
HOST, PORT = "127.0.0.1", 18080
EXPECT = "EAV HTTP OK 42"


def _wait_for_port(deadline):
    while time.time() < deadline:
        try:
            with socket.create_connection((HOST, PORT), timeout=1):
                return True
        except OSError:
            time.sleep(0.5)
    return False


def _raw_http(request_bytes):
    with socket.create_connection((HOST, PORT), timeout=5) as conn:
        conn.sendall(request_bytes)
        conn.shutdown(socket.SHUT_WR)
        response = b""
        while True:
            chunk = conn.recv(4096)
            if not chunk:
                break
            response += chunk
    return response.decode("iso-8859-1", "replace")


def _status_code(response_text):
    first = response_text.splitlines()[0] if response_text else ""
    parts = first.split()
    return int(parts[1]) if len(parts) >= 2 and parts[1].isdigit() else 0


def main():
    # First run compiles the native HTTP runtime (slow); allow plenty of time.
    proc = subprocess.Popen([sys.executable, SEMANTICSCRIPT, "run", SERVER])
    try:
        if not _wait_for_port(time.time() + 240):
            print("FAIL: server did not bind 127.0.0.1:%d" % PORT)
            return 1
        try:
            with urllib.request.urlopen("http://%s:%d/" % (HOST, PORT), timeout=5) as r:
                status = r.status
                body = r.read().decode("utf-8", "replace")
        except Exception as exc:  # noqa: BLE001
            print("FAIL: request error: %r" % exc)
            return 1
        ok = status == 200 and EXPECT in body
        print("HTTP server: status=%d body=%r -> %s"
              % (status, body, "PASS" if ok else "FAIL"))
        if not ok:
            return 1

        # R-178: Content-Length bodies still dispatch normally, but any
        # unsupported Transfer-Encoding is rejected before the GET / handler can
        # return the fixed OK body. TE+CL ambiguity must fail closed too.
        cl = _raw_http(
            b"GET / HTTP/1.1\r\n"
            b"Host: 127.0.0.1\r\n"
            b"Content-Length: 5\r\n"
            b"Connection: close\r\n"
            b"\r\nhello"
        )
        chunked = _raw_http(
            b"GET / HTTP/1.1\r\n"
            b"Host: 127.0.0.1\r\n"
            b"Transfer-Encoding: chunked\r\n"
            b"Connection: close\r\n"
            b"\r\n5\r\nhello\r\n0\r\n\r\n"
        )
        te_cl = _raw_http(
            b"GET / HTTP/1.1\r\n"
            b"Host: 127.0.0.1\r\n"
            b"Transfer-Encoding: gzip\r\n"
            b"Content-Length: 5\r\n"
            b"Connection: close\r\n"
            b"\r\nhello"
        )
        cl_code = _status_code(cl)
        chunked_code = _status_code(chunked)
        te_cl_code = _status_code(te_cl)
        reject_ok = (
            cl_code == 200 and EXPECT in cl and
            400 <= chunked_code <= 599 and EXPECT not in chunked and
            400 <= te_cl_code <= 599 and EXPECT not in te_cl
        )
        print("HTTP server R-178: cl=%d chunked=%d te+cl=%d -> %s"
              % (cl_code, chunked_code, te_cl_code,
                 "PASS" if reject_ok else "FAIL"))
        return 0 if reject_ok else 1
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    raise SystemExit(main())
