import base64
import hashlib
import hmac
import json
import os
import socket
import sqlite3
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
TEST_JWT_SECRET = "e2e-secret-with-at-least-thirty-two-bytes"


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
    for suffix in ["", "-wal", "-shm"]:
        db_path = SERVER_DIR / f"auction_arena.sqlite3{suffix}"
        if db_path.exists():
            db_path.unlink()

    kwargs = {
        "cwd": SERVER_DIR,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "env": {**os.environ, "AUCTION_ARENA_JWT_SECRET": TEST_JWT_SECRET},
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


def request_without_request_id(path, method="GET", body=None, headers=None, timeout=3):
    data = None
    merged_headers = {}
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


def expect_json(path, status, ok=None, code=None, method="GET", body=None, headers=None, route_path=None):
    actual_status, response_headers, text = request(
        path,
        method=method,
        body=body,
        headers=headers,
    )
    assert actual_status == status, f"{path}: expected {status}, got {actual_status}: {text}"
    assert_common_headers(response_headers, route_path or path)
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


def assert_hs256_signature(token, secret):
    header_payload, signature = token.rsplit(".", 1)
    digest = hmac.new(secret.encode("utf-8"), header_payload.encode("ascii"), hashlib.sha256).digest()
    expected = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    assert hmac.compare_digest(signature, expected)


def login_as(username):
    return expect_json(
        "/api/v1/auth/login",
        200,
        ok=True,
        method="POST",
        body=json.dumps({"username": username, "password": "auctioneer-demo-password"}),
    )


def post_auction_command(path, body, headers, key, status, ok, code=None):
    return expect_json(
        path,
        status,
        ok=ok,
        code=code,
        method="POST",
        body=json.dumps(body, separators=(",", ":")),
        headers={**headers, "Idempotency-Key": key},
    )


def registered_method_not_allowed_cases():
    cases = []
    main_source = SERVER_DIR / "src" / "main.sem"
    for line in main_source.read_text(encoding="utf-8").splitlines():
        if not line.startswith("route realtimeAuctionArenaServer "):
            continue
        if not line.endswith(" methodNotAllowedHandler"):
            continue
        method = line.split()[2]
        route_pattern = line.split('"')[1]
        path = (
            route_pattern
            .replace(":auctionId", "auc_method_matrix")
            .replace(":messageId", "msg_method_matrix")
        )
        cases.append((method, path))
    return cases


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
    assert "GET /api/v1/auctions/:auctionId" in route_text
    assert "POST /api/v1/auctions/:auctionId/start" in route_text
    assert "POST /api/v1/auctions/:auctionId/extend" in route_text
    assert "POST /api/v1/auctions/:auctionId/close" in route_text
    assert "POST /api/v1/auctions/:auctionId/bids" in route_text
    assert "GET /api/v1/auctions/:auctionId/events" in route_text
    assert "POST /api/v1/auctions/:auctionId/chat/messages" in route_text
    assert "DELETE /api/v1/auctions/:auctionId/chat/messages/:messageId" in route_text
    assert "POST /api/v1/auctions/:auctionId/chat/messages/:messageId/report" in route_text

    expect_json("/api/v1/auctions", 401, ok=False, code="unauthorized")

    not_found = expect_json("/api/v1/not-found", 404, ok=False, code="not_found")
    assert not_found["data"] is None

    expect_json("/api/v1/auth/login", 405, ok=False, code="method_not_allowed")
    expect_json("/healthz", 405, ok=False, code="method_not_allowed", method="POST")
    expect_json("/api/v1/auctions", 405, ok=False, code="method_not_allowed", method="DELETE")
    expect_json(
        "/api/v1/auctions/auc_method/extend",
        405,
        ok=False,
        code="method_not_allowed",
    )
    expect_json(
        "/api/v1/auctions/auc_method/close",
        405,
        ok=False,
        code="method_not_allowed",
    )


def test_registered_method_not_allowed_routes():
    cases = registered_method_not_allowed_cases()
    assert len(cases) >= 80, f"expected broad method guard matrix, got {len(cases)}"
    for method, path in cases:
        expect_json(path, 405, ok=False, code="method_not_allowed", method=method)


def test_generated_request_id_without_client_header():
    status, headers, text = request_without_request_id("/healthz")
    assert status == 200
    assert_header(headers, "X-Api-Version", "v1")
    generated = headers.get("X-Request-Id")
    assert generated
    assert generated != REQUEST_ID
    assert generated != "req_runtime_header_unavailable"
    assert_envelope(text, ok=True)

    login = login_as("auctioneer")
    auth = {"Authorization": f"Bearer {login['data']['accessToken']}"}
    status, headers, text = request_without_request_id("/api/v1/auctions", headers=auth)
    assert status == 200
    generated = headers.get("X-Request-Id")
    assert generated
    payload = assert_envelope(text, ok=True)
    assert payload["requestId"] == generated


def test_metrics_route():
    status, headers, text = request("/metrics")
    assert status == 200
    assert_common_headers(headers, "/metrics")
    assert "auction_server_bootstrap_info" in text
    assert 'auction_server_bootstrap_info{api_version="v1",runtime="native_http_exact_routes"} 1' in text
    assert 'auction_server_runtime_gap{feature="long_lived_sse"} 1' in text
    assert 'auction_server_runtime_gap{feature="durable_auth_sessions"} 1' in text
    assert "http_requests_total " in text
    assert 'auth_attempts_total{route="POST /api/v1/auth/login",outcome="accepted"}' in text
    assert 'auth_attempts_total{route="POST /api/v1/auth/login",outcome="rejected"}' in text
    assert 'auction_commands_total{outcome="accepted"}' in text
    assert 'auction_commands_total{outcome="rejected"}' in text
    assert "auction_bids_total" in text
    assert "rate_limit_hits_total " in text
    assert "active_sse_clients " in text
    assert "auction_server_sse_slow_client_drops_total 0" in text
    assert "auction_server_sse_subscriber_queue_capacity 256" in text
    assert "auction_server_sse_heartbeat_millis 15000" in text
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
    for attempt in range(10):
        expect_json(
            "/api/v1/auth/login",
            401,
            ok=False,
            code="invalid_credentials",
            method="POST",
            body=json.dumps({"username": "rate-limit-probe", "password": f"wrong-{attempt}"}),
        )
    expect_json(
        "/api/v1/auth/login",
        429,
        ok=False,
        code="rate_limited",
        method="POST",
        body=json.dumps({"username": "rate-limit-probe", "password": "wrong-limited"}),
    )

    before_login_seconds = int(time.time())
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
    assert_hs256_signature(login["data"]["accessToken"], TEST_JWT_SECRET)
    assert len(login["data"]["refreshToken"]) == 43
    assert login["data"]["user"]["role"] == "auctioneer"
    token_payload = decode_jwt_payload(login["data"]["accessToken"])
    assert token_payload["iss"] == "realtime-auction-arena"
    assert token_payload["aud"] == "api-v1"
    assert token_payload["sub"] == "user_auctioneer_001"
    assert token_payload["role"] == "auctioneer"
    assert token_payload["scopes"] == ["auctions:write", "bids:read", "chat:moderate"]
    assert "bids:write" not in token_payload["scopes"]
    assert before_login_seconds - 1 <= token_payload["iat"] <= int(time.time()) + 1
    assert token_payload["nbf"] == token_payload["iat"]
    assert token_payload["exp"] == token_payload["iat"] + 900
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
    refresh_payload = decode_jwt_payload(refresh["data"]["accessToken"])
    assert_hs256_signature(refresh["data"]["accessToken"], TEST_JWT_SECRET)
    assert refresh_payload["exp"] == refresh_payload["iat"] + 900
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

    active_headers = refreshed_bearer_headers
    logout_refresh_token = refresh["data"]["refreshToken"]

    empty_auctions = expect_json("/api/v1/auctions", 200, ok=True, headers=active_headers)
    assert empty_auctions["data"]["auctions"] == []

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
        401,
        ok=False,
        code="unauthorized",
        method="POST",
        body="{}",
        headers={"Idempotency-Key": "idem_e2e_create_001"},
    )
    expect_json(
        "/api/v1/auctions/auc_missing_start/start",
        400,
        ok=False,
        code="missing_idempotency_key",
        method="POST",
        body='{"expectedRevision":0}',
    )
    expect_json(
        "/api/v1/auctions/auc_missing_extend/extend",
        400,
        ok=False,
        code="missing_idempotency_key",
        method="POST",
        body='{"expectedRevision":0,"extendByMillis":60000}',
    )
    expect_json(
        "/api/v1/auctions/auc_missing_close/close",
        400,
        ok=False,
        code="missing_idempotency_key",
        method="POST",
        body='{"expectedRevision":0}',
    )
    expect_json(
        "/api/v1/auctions/auc_missing_bid/bids",
        400,
        ok=False,
        code="missing_idempotency_key",
        method="POST",
        body='{"amount":120,"expectedRevision":0}',
    )
    expect_json(
        "/api/v1/auctions/auc_missing_chat/chat/messages",
        400,
        ok=False,
        code="missing_idempotency_key",
        method="POST",
        body='{"text":"hello"}',
    )
    expect_json(
        "/api/v1/auctions/auc_missing_chat/chat/messages/msg_missing",
        400,
        ok=False,
        code="missing_idempotency_key",
        method="DELETE",
    )
    expect_json(
        "/api/v1/auctions/auc_missing_chat/chat/messages/msg_missing/report",
        400,
        ok=False,
        code="missing_idempotency_key",
        method="POST",
        body="{}",
    )

    create_body = json.dumps(
        {
            "title": "Vintage Synth",
            "description": "Demo auction",
            "startingBid": 100,
            "minimumIncrement": 10,
            "maxBidAmount": 1000,
            "startsAtUtcMillis": 1,
            "closesAtUtcMillis": 999999999999,
            "antiSnipingWindowMillis": 60000,
            "antiSnipingExtensionMillis": 60000,
        },
        separators=(",", ":"),
    )
    create_headers = {**active_headers, "Idempotency-Key": "idem_e2e_create_001"}
    created = expect_json(
        "/api/v1/auctions",
        201,
        ok=True,
        method="POST",
        body=create_body,
        headers=create_headers,
    )
    auction_id = created["data"]["auction"]["auctionId"]
    assert auction_id.startswith("auc_")
    assert created["data"]["auction"]["revision"] == 0

    create_unknown = json.loads(create_body)
    create_unknown["unexpected"] = True
    expect_json(
        "/api/v1/auctions",
        400,
        ok=False,
        code="validation_failed",
        method="POST",
        body=json.dumps(create_unknown, separators=(",", ":")),
        headers={**active_headers, "Idempotency-Key": "idem_e2e_create_unknown_001"},
    )

    replayed = expect_json(
        "/api/v1/auctions",
        201,
        ok=True,
        method="POST",
        body=create_body,
        headers=create_headers,
    )
    assert replayed["data"]["auction"]["auctionId"] == auction_id

    conflict_body = create_body.replace("Vintage Synth", "Different Synth")
    expect_json(
        "/api/v1/auctions",
        409,
        ok=False,
        code="idempotency_conflict",
        method="POST",
        body=conflict_body,
        headers=create_headers,
    )

    expect_json("/api/v1/auctions/auc_missing_snapshot", 404, ok=False, code="auction_not_found", headers=active_headers)
    expect_json(
        "/api/v1/auctions/auc_missing_for_events/events",
        404,
        ok=False,
        code="auction_not_found",
        headers=active_headers,
    )
    expect_json(
        "/api/v1/auctions/auc_missing_for_events/events",
        401,
        ok=False,
        code="unauthorized",
    )
    post_auction_command(
        "/api/v1/auctions/auc_missing_start/start",
        {"expectedRevision": 0},
        active_headers,
        "idem_e2e_start_missing_001",
        404,
        False,
        code="auction_not_found",
    )
    post_auction_command(
        "/api/v1/auctions/auc_missing_extend/extend",
        {"expectedRevision": 0, "extendByMillis": 60000},
        active_headers,
        "idem_e2e_extend_missing_001",
        404,
        False,
        code="auction_not_found",
    )
    post_auction_command(
        "/api/v1/auctions/auc_missing_close/close",
        {"expectedRevision": 0},
        active_headers,
        "idem_e2e_close_missing_001",
        404,
        False,
        code="auction_not_found",
    )
    relogin = login_as("auctioneer")
    active_headers = {"Authorization": f"Bearer {relogin['data']['accessToken']}"}
    logout_refresh_token = relogin["data"]["refreshToken"]

    listed = expect_json("/api/v1/auctions", 200, ok=True, headers=active_headers)
    assert listed["data"]["count"] == 1
    assert listed["data"]["auctions"][0]["auctionId"] == auction_id

    snapshot = expect_json(f"/api/v1/auctions/{auction_id}", 200, ok=True, headers=active_headers)
    assert snapshot["data"]["auction"]["statusCode"] == 1

    bidder_login = login_as("bidder")
    bidder_headers = {"Authorization": f"Bearer {bidder_login['data']['accessToken']}"}
    bidder_payload = decode_jwt_payload(bidder_login["data"]["accessToken"])
    assert bidder_payload["sub"] == "user_bidder_demo"
    assert bidder_payload["role"] == "bidder"
    assert bidder_payload["scopes"] == ["auctions:read", "bids:write", "chat:write"]
    bidder_session = expect_json("/api/v1/session", 200, ok=True, headers=bidder_headers)
    assert bidder_session["data"]["user"]["role"] == "bidder"

    post_auction_command(
        "/api/v1/auctions/auc_missing_bid/bids",
        {"amount": 120, "expectedRevision": 0},
        bidder_headers,
        "idem_e2e_bid_missing_001",
        404,
        False,
        code="auction_not_found",
    )
    post_auction_command(
        f"/api/v1/auctions/{auction_id}/bids",
        {"amount": 120, "expectedRevision": 0},
        bidder_headers,
        "idem_e2e_bid_before_start_001",
        409,
        False,
        code="auction_not_running",
    )

    relogin = login_as("auctioneer")
    active_headers = {"Authorization": f"Bearer {relogin['data']['accessToken']}"}
    logout_refresh_token = relogin["data"]["refreshToken"]

    start_body = {"expectedRevision": 0}
    started = post_auction_command(
        f"/api/v1/auctions/{auction_id}/start",
        start_body,
        active_headers,
        "idem_e2e_start_001",
        200,
        True,
    )
    assert started["data"]["auction"]["revision"] == 1

    replayed_start = post_auction_command(
        f"/api/v1/auctions/{auction_id}/start",
        start_body,
        active_headers,
        "idem_e2e_start_001",
        200,
        True,
    )
    assert replayed_start["data"]["auction"]["revision"] == 1
    post_auction_command(
        f"/api/v1/auctions/{auction_id}/start",
        {"expectedRevision": 1},
        active_headers,
        "idem_e2e_start_001",
        409,
        False,
        code="idempotency_conflict",
    )
    post_auction_command(
        f"/api/v1/auctions/{auction_id}/start",
        {"expectedRevision": 0},
        active_headers,
        "idem_e2e_start_stale_001",
        409,
        False,
        code="stale_revision",
    )
    post_auction_command(
        f"/api/v1/auctions/{auction_id}/start",
        {"expectedRevision": 1, "unexpected": True},
        active_headers,
        "idem_e2e_start_unknown_001",
        400,
        False,
        code="validation_failed",
    )
    post_auction_command(
        f"/api/v1/auctions/{auction_id}/extend",
        {"expectedRevision": 1, "extendByMillis": 0},
        active_headers,
        "idem_e2e_extend_bounds_001",
        400,
        False,
        code="extension_out_of_bounds",
    )
    post_auction_command(
        f"/api/v1/auctions/{auction_id}/extend",
        {"expectedRevision": 1, "extendByMillis": 60000, "unexpected": True},
        active_headers,
        "idem_e2e_extend_unknown_001",
        400,
        False,
        code="validation_failed",
    )

    extend_body = {"expectedRevision": 1, "extendByMillis": 60000}
    extended = post_auction_command(
        f"/api/v1/auctions/{auction_id}/extend",
        extend_body,
        active_headers,
        "idem_e2e_extend_001",
        200,
        True,
    )
    assert extended["data"]["auction"]["revision"] == 2
    assert extended["data"]["auction"]["statusCode"] == 2
    assert extended["data"]["extension"]["extendByMillis"] == 60000
    assert (
        extended["data"]["extension"]["newClosesAtUtcMillis"]
        - extended["data"]["extension"]["previousClosesAtUtcMillis"]
        == 60000
    )

    replayed_extend = post_auction_command(
        f"/api/v1/auctions/{auction_id}/extend",
        extend_body,
        active_headers,
        "idem_e2e_extend_001",
        200,
        True,
    )
    assert replayed_extend["data"]["auction"]["revision"] == 2
    post_auction_command(
        f"/api/v1/auctions/{auction_id}/extend",
        {"expectedRevision": 1, "extendByMillis": 120000},
        active_headers,
        "idem_e2e_extend_001",
        409,
        False,
        code="idempotency_conflict",
    )
    post_auction_command(
        f"/api/v1/auctions/{auction_id}/extend",
        {"expectedRevision": 1, "extendByMillis": 60000},
        active_headers,
        "idem_e2e_extend_stale_001",
        409,
        False,
        code="stale_revision",
    )

    post_auction_command(
        f"/api/v1/auctions/{auction_id}/bids",
        {"amount": 120, "expectedRevision": 2},
        active_headers,
        "idem_e2e_auctioneer_bid_denied_001",
        401,
        False,
        code="unauthorized",
    )

    bidder_login = login_as("bidder")
    active_headers = {"Authorization": f"Bearer {bidder_login['data']['accessToken']}"}
    logout_refresh_token = bidder_login["data"]["refreshToken"]

    post_auction_command(
        f"/api/v1/auctions/{auction_id}/bids",
        {"amount": 100, "expectedRevision": 2},
        active_headers,
        "idem_e2e_bid_below_min_001",
        409,
        False,
        code="bid_below_minimum",
    )
    post_auction_command(
        f"/api/v1/auctions/{auction_id}/bids",
        {"amount": 1001, "expectedRevision": 2},
        active_headers,
        "idem_e2e_bid_above_max_001",
        409,
        False,
        code="amount_too_high",
    )
    post_auction_command(
        f"/api/v1/auctions/{auction_id}/bids",
        {"amount": 120, "expectedRevision": 2, "unexpected": True},
        active_headers,
        "idem_e2e_bid_unknown_001",
        400,
        False,
        code="validation_failed",
    )

    bid_body = {"amount": 120, "expectedRevision": 2}
    bid = post_auction_command(
        f"/api/v1/auctions/{auction_id}/bids",
        bid_body,
        active_headers,
        "idem_e2e_bid_001",
        201,
        True,
    )
    assert bid["data"]["bid"]["accepted"] is True
    assert bid["data"]["auction"]["revision"] == 3

    replayed_bid = post_auction_command(
        f"/api/v1/auctions/{auction_id}/bids",
        bid_body,
        active_headers,
        "idem_e2e_bid_001",
        201,
        True,
    )
    assert replayed_bid["data"]["bid"]["bidId"] == bid["data"]["bid"]["bidId"]
    post_auction_command(
        f"/api/v1/auctions/{auction_id}/bids",
        {"amount": 130, "expectedRevision": 2},
        active_headers,
        "idem_e2e_bid_001",
        409,
        False,
        code="idempotency_conflict",
    )
    post_auction_command(
        f"/api/v1/auctions/{auction_id}/bids",
        {"amount": 140, "expectedRevision": 2},
        active_headers,
        "idem_e2e_bid_stale_001",
        409,
        False,
        code="stale_revision",
    )

    same_bidder_bid = post_auction_command(
        f"/api/v1/auctions/{auction_id}/bids",
        {"amount": 140, "expectedRevision": 3},
        active_headers,
        "idem_e2e_bid_same_bidder_001",
        201,
        True,
    )
    assert same_bidder_bid["data"]["bid"]["accepted"] is True
    assert same_bidder_bid["data"]["auction"]["revision"] == 4

    chat_created = post_auction_command(
        f"/api/v1/auctions/{auction_id}/chat/messages",
        {"text": "e2e chat message"},
        active_headers,
        "idem_e2e_chat_create_001",
        201,
        True,
    )
    assert chat_created["data"]["message"]["status"] == "created"
    assert chat_created["data"]["message"]["auctionId"] == auction_id
    expect_json(
        f"/api/v1/auctions/{auction_id}/chat/messages/msg_missing",
        404,
        ok=False,
        code="message_not_found",
        method="DELETE",
        headers={**active_headers, "Idempotency-Key": "idem_e2e_chat_delete_guard_001"},
    )
    expect_json(
        f"/api/v1/auctions/{auction_id}/chat/messages/msg_missing/report",
        404,
        ok=False,
        code="message_not_found",
        method="POST",
        body=json.dumps({"reason": "spam"}, separators=(",", ":")),
        headers={**active_headers, "Idempotency-Key": "idem_e2e_chat_report_guard_001"},
    )

    relogin = login_as("auctioneer")
    active_headers = {"Authorization": f"Bearer {relogin['data']['accessToken']}"}
    logout_refresh_token = relogin["data"]["refreshToken"]

    post_auction_command(
        f"/api/v1/auctions/{auction_id}/close",
        {"expectedRevision": 3},
        active_headers,
        "idem_e2e_close_stale_001",
        409,
        False,
        code="stale_revision",
    )
    close_body = {"expectedRevision": 4}
    closed = post_auction_command(
        f"/api/v1/auctions/{auction_id}/close",
        close_body,
        active_headers,
        "idem_e2e_close_001",
        200,
        True,
    )
    assert closed["data"]["auction"]["revision"] == 5
    assert closed["data"]["auction"]["statusCode"] == 3
    assert closed["data"]["auction"]["currentBid"] == 140
    assert closed["data"]["auction"]["winnerUserId"] == "user_bidder_demo"

    replayed_close = post_auction_command(
        f"/api/v1/auctions/{auction_id}/close",
        close_body,
        active_headers,
        "idem_e2e_close_001",
        200,
        True,
    )
    assert replayed_close["data"]["auction"]["revision"] == 5
    post_auction_command(
        f"/api/v1/auctions/{auction_id}/close",
        {"expectedRevision": 5},
        active_headers,
        "idem_e2e_close_001",
        409,
        False,
        code="idempotency_conflict",
    )
    post_auction_command(
        f"/api/v1/auctions/{auction_id}/close",
        {"expectedRevision": 5},
        active_headers,
        "idem_e2e_close_again_001",
        409,
        False,
        code="lifecycle_rejected",
    )
    post_auction_command(
        f"/api/v1/auctions/{auction_id}/close",
        {"expectedRevision": 5, "unexpected": True},
        active_headers,
        "idem_e2e_close_unknown_001",
        400,
        False,
        code="validation_failed",
    )

    bidder_login = login_as("bidder")
    bidder_headers = {"Authorization": f"Bearer {bidder_login['data']['accessToken']}"}
    active_headers = bidder_headers
    logout_refresh_token = bidder_login["data"]["refreshToken"]
    post_auction_command(
        f"/api/v1/auctions/{auction_id}/bids",
        {"amount": 160, "expectedRevision": 5},
        bidder_headers,
        "idem_e2e_bid_after_close_001",
        409,
        False,
        code="auction_not_running",
    )

    events = expect_json(f"/api/v1/auctions/{auction_id}/events", 200, ok=True, headers=active_headers)
    assert events["data"]["count"] == 7
    assert events["data"]["after"] == 0
    assert events["data"]["limit"] == 200
    assert events["data"]["nextAfter"] == 7
    assert [event["eventTypeCode"] for event in events["data"]["events"]] == [1, 2, 3, 5, 5, 8, 4]
    assert [event["eventType"] for event in events["data"]["events"]] == [
        "auction.created",
        "auction.started",
        "auction.extended",
        "bid.accepted",
        "bid.accepted",
        "chat.message.created",
        "auction.closed",
    ]
    after_events_path = f"/api/v1/auctions/{auction_id}/events?after=2&limit=2"
    after_events = expect_json(
        after_events_path,
        200,
        ok=True,
        headers=active_headers,
        route_path=f"/api/v1/auctions/{auction_id}/events",
    )
    assert after_events["data"]["after"] == 2
    assert after_events["data"]["limit"] == 2
    assert after_events["data"]["count"] == 2
    assert after_events["data"]["nextAfter"] == 4
    assert [event["sequence"] for event in after_events["data"]["events"]] == [3, 4]
    assert [event["eventTypeCode"] for event in after_events["data"]["events"]] == [3, 5]
    assert [event["eventType"] for event in after_events["data"]["events"]] == ["auction.extended", "bid.accepted"]
    expect_json(
        f"/api/v1/auctions/{auction_id}/events?limit=0",
        400,
        ok=False,
        code="validation_failed",
        headers=active_headers,
        route_path=f"/api/v1/auctions/{auction_id}/events",
    )
    expect_json(
        f"/api/v1/auctions/{auction_id}/events?after=-1",
        400,
        ok=False,
        code="validation_failed",
        headers=active_headers,
        route_path=f"/api/v1/auctions/{auction_id}/events",
    )
    last_event_id_events = expect_json(
        f"/api/v1/auctions/{auction_id}/events?after=1",
        200,
        ok=True,
        headers={**active_headers, "Last-Event-ID": "3"},
        route_path=f"/api/v1/auctions/{auction_id}/events",
    )
    assert last_event_id_events["data"]["after"] == 3
    assert last_event_id_events["data"]["count"] == 4
    assert [event["sequence"] for event in last_event_id_events["data"]["events"]] == [4, 5, 6, 7]
    db_path = SERVER_DIR / "auction_arena.sqlite3"
    with sqlite3.connect(db_path) as conn:
        seed_users = set(conn.execute("SELECT user_id, username, role FROM users").fetchall())
        assert ("user_auctioneer_001", "auctioneer", 20) in seed_users
        assert ("user_bidder_demo", "bidder", 10) in seed_users
        credential_users = set(conn.execute("SELECT user_id FROM password_credentials").fetchall())
        assert ("user_auctioneer_001",) in credential_users
        assert ("user_bidder_demo",) in credential_users

        audit_rows = conn.execute(
            """
            SELECT action, actor_user_id, actor_role, auction_id, bid_id, outcome
            FROM audit_events
            WHERE auction_id = ? AND outcome = 1
            """,
            (auction_id,),
        ).fetchall()
        assert len(audit_rows) == 6
        create_audit = [row for row in audit_rows if row[0] == "auction.create"]
        start_audit = [row for row in audit_rows if row[0] == "auction.start"]
        extend_audit = [row for row in audit_rows if row[0] == "auction.extend"]
        close_audit = [row for row in audit_rows if row[0] == "auction.close"]
        bid_audits = [row for row in audit_rows if row[0] == "bid.accepted"]
        assert len(create_audit) == 1
        assert len(start_audit) == 1
        assert len(extend_audit) == 1
        assert len(close_audit) == 1
        assert len(bid_audits) == 2
        assert create_audit[0][1:] == (
            "user_auctioneer_001",
            20,
            auction_id,
            "",
            1,
        )
        assert start_audit[0][1:] == (
            "user_auctioneer_001",
            20,
            auction_id,
            "",
            1,
        )
        assert extend_audit[0][1:] == (
            "user_auctioneer_001",
            20,
            auction_id,
            "",
            1,
        )
        assert close_audit[0][1:] == (
            "user_auctioneer_001",
            20,
            auction_id,
            "",
            1,
        )
        for bid_audit in bid_audits:
            assert bid_audit[1] == "user_bidder_demo"
            assert bid_audit[2] == 10
            assert bid_audit[3] == auction_id
            assert bid_audit[4].startswith("bid_")
            assert bid_audit[5] == 1
        rejected_audit_rows = conn.execute(
            """
            SELECT action, outcome, error_code, payload_json
            FROM audit_events
            WHERE auction_id = ? AND outcome IN (2, 3, 4)
            """,
            (auction_id,),
        ).fetchall()
        assert rejected_audit_rows
        assert all(row[2] for row in rejected_audit_rows)
        assert all("auctioneer-demo-password" not in row[3] for row in rejected_audit_rows)

        idem_rows = conn.execute(
            """
            SELECT scope, key, actor_user_id, auction_id
            FROM idempotency_keys
            WHERE key IN (?, ?, ?, ?, ?, ?)
            """,
            (
                "idem_e2e_create_001",
                "idem_e2e_start_001",
                "idem_e2e_extend_001",
                "idem_e2e_bid_001",
                "idem_e2e_bid_same_bidder_001",
                "idem_e2e_close_001",
            ),
        ).fetchall()
        assert {
            ("auction.create", "idem_e2e_create_001", "user_auctioneer_001", ""),
            ("auction.start", "idem_e2e_start_001", "user_auctioneer_001", auction_id),
            ("auction.extend", "idem_e2e_extend_001", "user_auctioneer_001", auction_id),
            ("auction.bid", "idem_e2e_bid_001", "user_bidder_demo", auction_id),
            ("auction.bid", "idem_e2e_bid_same_bidder_001", "user_bidder_demo", auction_id),
            ("auction.close", "idem_e2e_close_001", "user_auctioneer_001", auction_id),
        } == set(idem_rows)

        request_log_rows = conn.execute(
            """
            SELECT route_pattern, status, actor_user_id, duration_ms, error_code,
                   ip_address_hash, user_agent_hash
            FROM request_log
            WHERE auction_id = ?
            """,
            (auction_id,),
        ).fetchall()
        comparable_request_log_rows = {row[:5] for row in request_log_rows}
        assert {
            ("/api/v1/auctions", 201, "user_auctioneer_001", 0, ""),
            ("/api/v1/auctions/:auctionId/start", 200, "user_auctioneer_001", 0, ""),
            ("/api/v1/auctions/:auctionId/extend", 200, "user_auctioneer_001", 0, ""),
            ("/api/v1/auctions/:auctionId/close", 200, "user_auctioneer_001", 0, ""),
            ("/api/v1/auctions/:auctionId/bids", 201, "user_bidder_demo", 0, ""),
            ("/api/v1/auctions/:auctionId/bids", 409, "user_bidder_demo", 0, "auction_not_running"),
            ("/api/v1/auctions/:auctionId/bids", 409, "user_bidder_demo", 0, "bid_below_minimum"),
            ("/api/v1/auctions/:auctionId/bids", 409, "user_bidder_demo", 0, "amount_too_high"),
            ("/api/v1/auctions/:auctionId/bids", 409, "user_bidder_demo", 0, "stale_revision"),
        }.issubset(comparable_request_log_rows)
        assert all(row[5] == "redacted" for row in request_log_rows)
        assert all(row[6] == "redacted" for row in request_log_rows)
        rejected_bid_rows = conn.execute(
            """
            SELECT status, reject_reason, bidder_user_id, amount_minor,
              auction_revision, request_id, error_code
            FROM bids
            WHERE auction_id = ? AND status = 2
            ORDER BY created_at
            """,
            (auction_id,),
        ).fetchall()
        assert (2, 2, "user_bidder_demo", 120, 0, "req_runtime_header_unavailable", "auction_not_running") in rejected_bid_rows
        assert (2, 4, "user_bidder_demo", 100, 2, "req_runtime_header_unavailable", "bid_below_minimum") in rejected_bid_rows
        assert (2, 5, "user_bidder_demo", 1001, 2, "req_runtime_header_unavailable", "amount_too_high") in rejected_bid_rows
        assert (2, 7, "user_bidder_demo", 140, 3, "req_runtime_header_unavailable", "stale_revision") in rejected_bid_rows
        assert (2, 2, "user_bidder_demo", 160, 5, "req_runtime_header_unavailable", "auction_not_running") in rejected_bid_rows

        rate_limit_count = conn.execute("SELECT count(*) FROM rate_limit_buckets").fetchone()[0]
        assert rate_limit_count >= 1
        bucket = conn.execute(
            "SELECT count, limit_count, reset_at FROM rate_limit_buckets WHERE bucket_key = 'rate-limit-probe'"
        ).fetchone()
        assert bucket[0] == 11
        assert bucket[1] == 10
        assert bucket[2] > 0
        auth_audit_actions = set(
            conn.execute(
                "SELECT action, outcome, error_code FROM audit_events WHERE action LIKE 'auth.login.%'"
            ).fetchall()
        )
        assert ("auth.login.accepted", 1, "") in auth_audit_actions
        assert ("auth.login.rejected", 4, "invalid_credentials") in auth_audit_actions
        assert ("auth.login.rejected", 4, "rate_limited") in auth_audit_actions

    logout = expect_json(
        "/api/v1/auth/logout",
        200,
        ok=True,
        method="POST",
        body=json.dumps({"refreshToken": logout_refresh_token}),
    )
    assert logout["data"]["loggedOut"] is True

    expect_json(
        "/api/v1/session",
        401,
        ok=False,
        code="unauthorized",
        headers=active_headers,
    )


def main():
    run_build()
    process = start_server()
    try:
        test_public_routes()
        test_registered_method_not_allowed_routes()
        test_auth_and_api_fail_closed()
        test_generated_request_id_without_client_header()
        test_metrics_route()
    finally:
        stop_server(process)
    print("E2E API smoke passed")


if __name__ == "__main__":
    main()
