import base64
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
SERVER_DIR = ROOT / "experiments" / "realtime-auction-arena" / "server"
EXE = SERVER_DIR / "build" / "realtime_auction_arena_server.exe"
BASE_URL = os.environ.get("AUCTION_ARENA_BASE_URL", "http://127.0.0.1:18083")
REQUEST_ID = "req_e2e_smoke"


def run_build():
    cmd = [
        sys.executable,
        "SemanticScript/tools/sem.py",
        "build",
        "experiments/realtime-auction-arena/server",
    ]
    subprocess.run(cmd, cwd=ROOT, check=True)


def port_is_open(host="127.0.0.1", port=18083):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        return sock.connect_ex((host, port)) == 0


def start_server():
    if port_is_open():
        raise RuntimeError("port 18083 is already in use; stop the existing server before E2E")
    if not EXE.exists():
        raise RuntimeError(f"server executable missing after build: {EXE}")

    kwargs = {
        "cwd": SERVER_DIR,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

    process = subprocess.Popen([str(EXE)], **kwargs)
    for _ in range(40):
        if process.poll() is not None:
            raise RuntimeError(f"server exited early with code {process.returncode}")
        try:
            status, _, _ = request("/healthz", timeout=1)
            if status == 200:
                return process
        except Exception:
            time.sleep(0.25)
    raise RuntimeError("server did not become ready on http://127.0.0.1:18083")


def stop_server(process):
    if process and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2)


def request(path, method="GET", body=None, headers=None, timeout=3):
    data = None
    merged_headers = {"X-Request-Id": REQUEST_ID}
    if headers:
        merged_headers.update(headers)
    if body is not None:
        data = body.encode("utf-8")
        merged_headers.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(
        BASE_URL + path,
        data=data,
        headers=merged_headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.status, dict(response.headers), response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), exc.read().decode("utf-8")


def assert_header(headers, name, expected):
    actual = headers.get(name)
    assert actual == expected, f"{name}: expected {expected!r}, got {actual!r}"


def assert_common_headers(headers, path):
    assert_header(headers, "X-Api-Version", "v1")
    assert_header(headers, "X-Request-Id", REQUEST_ID)
    assert_header(headers, "X-Max-Body-Bytes", "65536")
    assert_header(headers, "X-Route-Path", path)


def assert_envelope(text, ok=None, code=None):
    payload = json.loads(text)
    assert payload["apiVersion"] == "v1"
    assert "requestId" in payload
    assert "ok" in payload
    assert "data" in payload
    assert "error" in payload
    if ok is not None:
        assert payload["ok"] is ok, payload
    if code is not None:
        assert payload["error"]["code"] == code, payload
    return payload


def expect_json(path, status, ok=None, code=None, method="GET", body=None, headers=None):
    actual_status, response_headers, text = request(
        path,
        method=method,
        body=body,
        headers=headers,
    )
    assert actual_status == status, f"{path}: expected {status}, got {actual_status}: {text}"
    assert_common_headers(response_headers, path)
    payload = assert_envelope(text, ok=ok, code=code)
    print(f"PASS {method} {path} -> {status}")
    return payload


def tamper_token(token):
    replacement = "A" if token[-1] != "A" else "B"
    return token[:-1] + replacement


def decode_jwt_payload(token):
    payload_segment = token.split(".")[1]
    padded = payload_segment + "=" * (-len(payload_segment) % 4)
    return json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))


def test_public_routes():
    health = expect_json("/healthz", 200, ok=True)
    assert health["data"]["status"] == "ok"

    ready = expect_json("/readyz", 200, ok=True)
    assert ready["data"]["ready"] is True

    routes = expect_json("/api/v1", 200, ok=True)
    route_text = "\n".join(routes["data"]["routes"])
    assert "POST /api/v1/auth/login" in route_text
    assert "POST /api/v1/auth/refresh" in route_text
    assert "POST /api/v1/auth/logout" in route_text
    assert "GET /api/v1/session" in route_text
    assert "GET /api/v1/auctions" in route_text
    assert "POST /api/v1/auctions" in route_text

    auctions = expect_json("/api/v1/auctions", 200, ok=True)
    assert auctions["data"]["auctions"] == []

    not_found = expect_json("/api/v1/not-found", 404, ok=False, code="not_found")
    assert not_found["data"] is None


def test_metrics_route():
    status, headers, text = request("/metrics")
    assert status == 200
    assert_common_headers(headers, "/metrics")
    assert "auction_server_bootstrap_info" in text
    assert 'auction_server_bootstrap_info{api_version="v1",runtime="native_http_exact_routes"} 1' in text
    assert 'auction_server_runtime_gap{feature="long_lived_sse"} 1' in text
    assert 'auction_server_runtime_gap{feature="sqlite_persistence"} 1' in text
    assert 'auction_server_runtime_gap{feature="request_logging_counters"} 1' in text
    print("PASS GET /metrics -> 200")


def test_auth_and_api_fail_closed():
    expect_json("/api/v1/session", 401, ok=False, code="unauthorized")

    expect_json(
        "/api/v1/auth/login",
        401,
        ok=False,
        code="invalid_credentials",
        method="POST",
        body='{"username":"auctioneer","password":"wrong-password"}',
    )
    expect_json(
        "/api/v1/auth/login",
        415,
        ok=False,
        code="unsupported_media_type",
        method="POST",
        body='{"username":"auctioneer","password":"auctioneer-demo-password"}',
        headers={"Content-Type": "text/plain"},
    )
    expect_json(
        "/api/v1/auth/login",
        401,
        ok=False,
        code="invalid_credentials",
        method="POST",
        body=json.dumps({"username": "auctioneer", "password": "x" * 73}),
    )

    login = expect_json(
        "/api/v1/auth/login",
        200,
        ok=True,
        method="POST",
        body='{"username":"auctioneer","password":"auctioneer-demo-password"}',
    )
    assert login["data"]["tokenType"] == "Bearer"
    assert login["data"]["accessToken"].count(".") == 2
    assert login["data"]["crypto"] == "HS256"
    assert len(login["data"]["refreshToken"]) == 43
    assert login["data"]["user"]["role"] == "auctioneer"
    token_payload = decode_jwt_payload(login["data"]["accessToken"])
    assert token_payload["iss"] == "realtime-auction-arena"
    assert token_payload["aud"] == "api-v1"
    assert token_payload["sub"] == "user_auctioneer_001"
    assert token_payload["role"] == "auctioneer"
    assert token_payload["scopes"] == ["auctions:write", "bids:read", "chat:moderate"]
    assert "iat" in token_payload
    assert "nbf" in token_payload
    assert token_payload["exp"] == 2000000000
    assert "jti" in token_payload

    bearer_headers = {"Authorization": f"Bearer {login['data']['accessToken']}"}
    tampered_headers = {"Authorization": f"Bearer {tamper_token(login['data']['accessToken'])}"}
    expect_json(
        "/api/v1/session",
        401,
        ok=False,
        code="unauthorized",
        headers=tampered_headers,
    )

    session = expect_json(
        "/api/v1/session",
        200,
        ok=True,
        headers=bearer_headers,
    )
    assert session["data"]["authenticated"] is True
    assert session["data"]["user"]["username"] == "auctioneer"

    large_body = "x" * 70000
    expect_json(
        "/api/v1/auth/login",
        413,
        ok=False,
        code="payload_too_large",
        method="POST",
        body=large_body,
    )

    refresh = expect_json(
        "/api/v1/auth/refresh",
        200,
        ok=True,
        method="POST",
        body=json.dumps({"refreshToken": login["data"]["refreshToken"]}),
    )
    assert refresh["data"]["rotated"] is True
    assert refresh["data"]["accessToken"] != login["data"]["accessToken"]
    assert refresh["data"]["refreshToken"] != login["data"]["refreshToken"]
    expect_json(
        "/api/v1/auth/refresh",
        401,
        ok=False,
        code="invalid_refresh_token",
        method="POST",
        body=json.dumps({"refreshToken": login["data"]["refreshToken"]}),
    )
    expect_json("/api/v1/session", 401, ok=False, code="unauthorized", headers=bearer_headers)

    refreshed_bearer_headers = {"Authorization": f"Bearer {refresh['data']['accessToken']}"}
    refreshed_session = expect_json(
        "/api/v1/session",
        200,
        ok=True,
        headers=refreshed_bearer_headers,
    )
    assert refreshed_session["data"]["authenticated"] is True

    logout = expect_json(
        "/api/v1/auth/logout",
        200,
        ok=True,
        method="POST",
        body=json.dumps({"refreshToken": refresh["data"]["refreshToken"]}),
    )
    assert logout["data"]["loggedOut"] is True

    expect_json(
        "/api/v1/session",
        401,
        ok=False,
        code="unauthorized",
        headers=refreshed_bearer_headers,
    )
    expect_json(
        "/api/v1/auctions",
        400,
        ok=False,
        code="missing_idempotency_key",
        method="POST",
        body="{}",
    )
    expect_json(
        "/api/v1/auctions",
        403,
        ok=False,
        code="forbidden",
        method="POST",
        body="{}",
        headers={"Idempotency-Key": "idem_e2e_create_001"},
    )


def main():
    run_build()
    process = start_server()
    try:
        test_public_routes()
        test_metrics_route()
        test_auth_and_api_fail_closed()
    finally:
        stop_server(process)
    print("E2E API smoke passed")


if __name__ == "__main__":
    main()
