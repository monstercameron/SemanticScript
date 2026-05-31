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

HERE = os.path.dirname(os.path.abspath(__file__))
SEMANTICSCRIPT = os.path.join(HERE, "semanticscript.py")
SERVER = os.path.join(HERE, "http_server_demo.sem")
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
        return 0 if ok else 1
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    raise SystemExit(main())
