import base64
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
    assert "POST /api/v1/auctions/:auctionId/bids" in route_text
    assert "GET /api/v1/auctions/:auctionId/events" in route_text

    expect_json("/api/v1/auctions", 401, ok=False, code="unauthorized")

    not_found = expect_json("/api/v1/not-found", 404, ok=False, code="not_found")
    assert not_found["data"] is None


def test_metrics_route():
    status, headers, text = request("/metrics")
    assert status == 200
    assert_common_headers(headers, "/metrics")
    assert "auction_server_bootstrap_info" in text
    assert 'auction_server_bootstrap_info{api_version="v1",runtime="native_http_exact_routes"} 1' in text
    assert 'auction_server_runtime_gap{feature="long_lived_sse"} 1' in text
    assert 'auction_server_runtime_gap{feature="request_logging_counters"} 1' in text
    assert 'auction_server_runtime_gap{feature="durable_auth_sessions"} 1' in text
    assert 'auction_server_runtime_gap{feature="chat_routes"} 1' in text
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
    assert "bids:write" not in token_payload["scopes"]
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
    post_auction_command(
        "/api/v1/auctions/auc_missing_start/start",
        {"expectedRevision": 0},
        active_headers,
        "idem_e2e_start_missing_001",
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
        f"/api/v1/auctions/{auction_id}/bids",
        {"amount": 120, "expectedRevision": 1},
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
        {"amount": 100, "expectedRevision": 1},
        active_headers,
        "idem_e2e_bid_below_min_001",
        409,
        False,
        code="bid_below_minimum",
    )
    post_auction_command(
        f"/api/v1/auctions/{auction_id}/bids",
        {"amount": 1001, "expectedRevision": 1},
        active_headers,
        "idem_e2e_bid_above_max_001",
        400,
        False,
        code="validation_failed",
    )

    bid_body = {"amount": 120, "expectedRevision": 1}
    bid = post_auction_command(
        f"/api/v1/auctions/{auction_id}/bids",
        bid_body,
        active_headers,
        "idem_e2e_bid_001",
        201,
        True,
    )
    assert bid["data"]["bid"]["accepted"] is True
    assert bid["data"]["auction"]["revision"] == 2

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
        {"amount": 130, "expectedRevision": 1},
        active_headers,
        "idem_e2e_bid_001",
        409,
        False,
        code="idempotency_conflict",
    )
    post_auction_command(
        f"/api/v1/auctions/{auction_id}/bids",
        {"amount": 140, "expectedRevision": 1},
        active_headers,
        "idem_e2e_bid_stale_001",
        409,
        False,
        code="stale_revision",
    )

    same_bidder_bid = post_auction_command(
        f"/api/v1/auctions/{auction_id}/bids",
        {"amount": 140, "expectedRevision": 2},
        active_headers,
        "idem_e2e_bid_same_bidder_001",
        201,
        True,
    )
    assert same_bidder_bid["data"]["bid"]["accepted"] is True
    assert same_bidder_bid["data"]["auction"]["revision"] == 3

    events = expect_json(f"/api/v1/auctions/{auction_id}/events", 200, ok=True, headers=active_headers)
    assert events["data"]["count"] == 4
    assert [event["eventTypeCode"] for event in events["data"]["events"]] == [1, 2, 5, 5]
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
            WHERE auction_id = ?
            """,
            (auction_id,),
        ).fetchall()
        assert len(audit_rows) == 4
        create_audit = [row for row in audit_rows if row[0] == "auction.create"]
        start_audit = [row for row in audit_rows if row[0] == "auction.start"]
        bid_audits = [row for row in audit_rows if row[0] == "bid.accepted"]
        assert len(create_audit) == 1
        assert len(start_audit) == 1
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
        for bid_audit in bid_audits:
            assert bid_audit[1] == "user_bidder_demo"
            assert bid_audit[2] == 10
            assert bid_audit[3] == auction_id
            assert bid_audit[4].startswith("bid_")
            assert bid_audit[5] == 1

        idem_rows = conn.execute(
            """
            SELECT scope, key, actor_user_id, auction_id
            FROM idempotency_keys
            WHERE key IN (?, ?, ?, ?)
            """,
            (
                "idem_e2e_create_001",
                "idem_e2e_start_001",
                "idem_e2e_bid_001",
                "idem_e2e_bid_same_bidder_001",
            ),
        ).fetchall()
        assert {
            ("auction.create", "idem_e2e_create_001", "user_auctioneer_001", ""),
            ("auction.start", "idem_e2e_start_001", "user_auctioneer_001", auction_id),
            ("auction.bid", "idem_e2e_bid_001", "user_bidder_demo", auction_id),
            ("auction.bid", "idem_e2e_bid_same_bidder_001", "user_bidder_demo", auction_id),
        } == set(idem_rows)

        request_log_count = conn.execute("SELECT count(*) FROM request_log").fetchone()[0]
        if request_log_count:
            logged_rows = conn.execute("SELECT route_pattern, status, started_at FROM request_log").fetchall()
            assert all(row[0] for row in logged_rows)
            assert all(row[1] >= 100 for row in logged_rows)
            assert all(row[2] >= 0 for row in logged_rows)

        rate_limit_count = conn.execute("SELECT count(*) FROM rate_limit_buckets").fetchone()[0]
        if rate_limit_count:
            bucket = conn.execute(
                "SELECT count, limit_count, reset_at FROM rate_limit_buckets ORDER BY reset_at DESC LIMIT 1"
            ).fetchone()
            assert bucket[0] >= 0
            assert bucket[1] > 0
            assert bucket[2] > 0

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
        test_metrics_route()
        test_auth_and_api_fail_closed()
    finally:
        stop_server(process)
    print("E2E API smoke passed")


if __name__ == "__main__":
    main()
