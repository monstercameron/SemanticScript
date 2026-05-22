import base64
import json
import os
import time
import uuid
import urllib.error
import urllib.request


BASE_URL = os.environ.get("AUCTION_ARENA_BASE_URL", "http://127.0.0.1:18083")
REQUEST_ID = "req_python_smoke"


def unique_key(prefix):
    return f"{prefix}_{uuid.uuid4().hex}"


def request(path, method="GET", body=None, headers=None):
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
        with urllib.request.urlopen(req, timeout=3) as response:
            return response.status, dict(response.headers), response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), exc.read().decode("utf-8")


def request_without_request_id(path, method="GET", body=None, headers=None):
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
        with urllib.request.urlopen(req, timeout=3) as response:
            return response.status, dict(response.headers), response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), exc.read().decode("utf-8")


def assert_envelope(text):
    payload = json.loads(text)
    assert payload["apiVersion"] == "v1"
    assert "requestId" in payload
    assert "ok" in payload
    assert "data" in payload
    assert "error" in payload
    return payload


def assert_common_headers(headers, path):
    assert headers.get("X-Api-Version") == "v1"
    assert headers.get("X-Request-Id") == REQUEST_ID
    assert headers.get("X-Max-Body-Bytes") == "65536"
    assert headers.get("X-Route-Path") == path


def expect_json(path, status, ok=None, code=None, method="GET", body=None, headers=None):
    actual_status, response_headers, text = request(
        path,
        method=method,
        body=body,
        headers=headers,
    )
    assert actual_status == status
    assert_common_headers(response_headers, path)
    payload = assert_envelope(text)
    if ok is not None:
        assert payload["ok"] is ok
    if code is not None:
        assert payload["error"]["code"] == code
    return payload


def tamper_token(token):
    replacement = "A" if token[-1] != "A" else "B"
    return token[:-1] + replacement


def decode_jwt_payload(token):
    payload_segment = token.split(".")[1]
    padded = payload_segment + "=" * (-len(payload_segment) % 4)
    return json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))


def login_as_auctioneer():
    return expect_json(
        "/api/v1/auth/login",
        200,
        ok=True,
        method="POST",
        body='{"username":"auctioneer","password":"auctioneer-demo-password"}',
    )


def login_as_bidder():
    return expect_json(
        "/api/v1/auth/login",
        200,
        ok=True,
        method="POST",
        body='{"username":"bidder","password":"auctioneer-demo-password"}',
    )


def auction_body(title, max_bid_amount=1000):
    return json.dumps(
        {
            "title": title,
            "description": "API harness auction",
            "startingBid": 100,
            "minimumIncrement": 10,
            "maxBidAmount": max_bid_amount,
            "startsAtUtcMillis": 1,
            "closesAtUtcMillis": 999999999999,
            "antiSnipingWindowMillis": 60000,
            "antiSnipingExtensionMillis": 60000,
        },
        separators=(",", ":"),
    )


def create_auction(auth, title, idempotency_key=None, max_bid_amount=1000):
    body = auction_body(title, max_bid_amount=max_bid_amount)
    headers = {**auth, "Idempotency-Key": idempotency_key or unique_key("idem_py_create")}
    payload = expect_json(
        "/api/v1/auctions",
        201,
        ok=True,
        method="POST",
        body=body,
        headers=headers,
    )
    return payload, body, headers


def post_auction_command(path, body, auth, key, status, ok, code=None):
    return expect_json(
        path,
        status,
        ok=ok,
        code=code,
        method="POST",
        body=json.dumps(body, separators=(",", ":")),
        headers={**auth, "Idempotency-Key": key},
    )


def test_health_ready_and_api_envelopes():
    for path in ["/healthz", "/readyz", "/api/v1"]:
        expect_json(path, 200, ok=True)
    login = login_as_auctioneer()
    expect_json(
        "/api/v1/auctions",
        200,
        ok=True,
        headers={"Authorization": f"Bearer {login['data']['accessToken']}"},
    )


def test_missing_request_id_gets_generated_header_and_dynamic_envelope():
    status, headers, text = request_without_request_id("/healthz")
    assert status == 200
    assert headers.get("X-Api-Version") == "v1"
    generated = headers.get("X-Request-Id")
    assert generated
    assert generated != REQUEST_ID
    assert generated != "req_runtime_header_unavailable"
    assert_envelope(text)

    login = login_as_auctioneer()
    auth = {"Authorization": f"Bearer {login['data']['accessToken']}"}
    status, headers, text = request_without_request_id("/api/v1/auctions", headers=auth)
    assert status == 200
    assert headers.get("X-Api-Version") == "v1"
    generated = headers.get("X-Request-Id")
    assert generated
    payload = assert_envelope(text)
    assert payload["requestId"] == generated


def test_api_index_only_asserts_executable_routes():
    payload = expect_json("/api/v1", 200, ok=True)
    route_text = "\n".join(payload["data"]["routes"])
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


def test_metrics_smoke():
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


def test_known_paths_reject_unsupported_methods():
    expect_json(
        "/api/v1/auth/login",
        405,
        ok=False,
        code="method_not_allowed",
        method="GET",
    )
    expect_json(
        "/healthz",
        405,
        ok=False,
        code="method_not_allowed",
        method="POST",
    )
    expect_json(
        "/api/v1/auctions",
        405,
        ok=False,
        code="method_not_allowed",
        method="DELETE",
    )


def test_auth_demo_flow_is_enveloped():
    before_login_seconds = int(time.time())
    payload = login_as_auctioneer()
    assert payload["data"]["tokenType"] == "Bearer"
    assert payload["data"]["accessToken"].count(".") == 2
    assert payload["data"]["crypto"] == "HS256"
    assert len(payload["data"]["refreshToken"]) == 43
    assert payload["data"]["user"]["username"] == "auctioneer"
    assert payload["data"]["user"]["role"] == "auctioneer"
    token_payload = decode_jwt_payload(payload["data"]["accessToken"])
    assert token_payload["iss"] == "realtime-auction-arena"
    assert token_payload["aud"] == "api-v1"
    assert token_payload["sub"] == "user_auctioneer_001"
    assert token_payload["role"] == "auctioneer"
    assert token_payload["scopes"] == ["auctions:write", "bids:read", "chat:moderate"]
    assert before_login_seconds - 1 <= token_payload["iat"] <= int(time.time()) + 1
    assert token_payload["nbf"] == token_payload["iat"]
    assert token_payload["exp"] == token_payload["iat"] + 900
    assert "jti" in token_payload


def test_bidder_demo_flow_is_enveloped():
    before_login_seconds = int(time.time())
    payload = login_as_bidder()
    assert payload["data"]["user"]["username"] == "bidder"
    assert payload["data"]["user"]["role"] == "bidder"
    token_payload = decode_jwt_payload(payload["data"]["accessToken"])
    assert token_payload["sub"] == "user_bidder_demo"
    assert token_payload["role"] == "bidder"
    assert token_payload["scopes"] == ["auctions:read", "bids:write", "chat:write"]
    assert before_login_seconds - 1 <= token_payload["iat"] <= int(time.time()) + 1
    assert token_payload["nbf"] == token_payload["iat"]
    assert token_payload["exp"] == token_payload["iat"] + 900
    session = expect_json(
        "/api/v1/session",
        200,
        ok=True,
        headers={"Authorization": f"Bearer {payload['data']['accessToken']}"},
    )
    assert session["data"]["user"]["username"] == "bidder"
    assert session["data"]["user"]["role"] == "bidder"


def test_auth_rejects_bad_password():
    payload = expect_json(
        "/api/v1/auth/login",
        401,
        ok=False,
        code="invalid_credentials",
        method="POST",
        body='{"username":"auctioneer","password":"wrong-password"}',
    )
    assert payload["data"] is None


def test_session_requires_authentication():
    expect_json("/api/v1/session", 401, ok=False, code="unauthorized")


def test_session_accepts_current_bearer_and_rejects_tampered_token():
    login = login_as_auctioneer()
    bearer_headers = {"Authorization": f"Bearer {login['data']['accessToken']}"}
    tampered_headers = {"Authorization": f"Bearer {tamper_token(login['data']['accessToken'])}"}

    expect_json(
        "/api/v1/session",
        401,
        ok=False,
        code="unauthorized",
        headers=tampered_headers,
    )

    session = expect_json("/api/v1/session", 200, ok=True, headers=bearer_headers)
    assert session["data"]["authenticated"] is True
    assert session["data"]["user"]["username"] == "auctioneer"


def test_refresh_rotation_rejects_replay_and_stales_old_access_token():
    login = login_as_auctioneer()
    original_bearer_headers = {"Authorization": f"Bearer {login['data']['accessToken']}"}

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
    expect_json(
        "/api/v1/session",
        401,
        ok=False,
        code="unauthorized",
        headers=original_bearer_headers,
    )

    refreshed_bearer_headers = {"Authorization": f"Bearer {refresh['data']['accessToken']}"}
    refreshed_session = expect_json(
        "/api/v1/session",
        200,
        ok=True,
        headers=refreshed_bearer_headers,
    )
    assert refreshed_session["data"]["authenticated"] is True


def test_logout_revokes_current_process_local_session():
    login = login_as_auctioneer()
    bearer_headers = {"Authorization": f"Bearer {login['data']['accessToken']}"}

    logout = expect_json(
        "/api/v1/auth/logout",
        200,
        ok=True,
        method="POST",
        body=json.dumps({"refreshToken": login["data"]["refreshToken"]}),
    )
    assert logout["data"]["loggedOut"] is True
    expect_json(
        "/api/v1/session",
        401,
        ok=False,
        code="unauthorized",
        headers=bearer_headers,
    )


def test_oversized_login_body_returns_413_envelope():
    payload = expect_json(
        "/api/v1/auth/login",
        413,
        ok=False,
        code="payload_too_large",
        method="POST",
        body="x" * 70000,
    )
    assert payload["data"] is None


def test_auction_create_start_bid_and_events_flow():
    login = login_as_auctioneer()
    auth = {"Authorization": f"Bearer {login['data']['accessToken']}"}
    token_payload = decode_jwt_payload(login["data"]["accessToken"])
    assert token_payload["role"] == "auctioneer"
    assert "bids:write" not in token_payload["scopes"]

    missing_key = expect_json(
        "/api/v1/auctions",
        400,
        ok=False,
        code="missing_idempotency_key",
        method="POST",
        body="{}",
    )
    assert missing_key["data"] is None
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

    unauthorized = expect_json(
        "/api/v1/auctions",
        401,
        ok=False,
        code="unauthorized",
        method="POST",
        body="{}",
        headers={"Idempotency-Key": "idem_py_create_001"},
    )
    assert unauthorized["data"] is None

    created, create_body, create_headers = create_auction(
        auth,
        f"Python Smoke Lot {uuid.uuid4().hex}",
        idempotency_key=unique_key("idem_py_create_flow"),
    )
    auction_id = created["data"]["auction"]["auctionId"]
    assert auction_id.startswith("auc_")

    create_unknown = json.loads(auction_body(f"Unknown Field Lot {uuid.uuid4().hex}"))
    create_unknown["unexpected"] = True
    expect_json(
        "/api/v1/auctions",
        400,
        ok=False,
        code="validation_failed",
        method="POST",
        body=json.dumps(create_unknown, separators=(",", ":")),
        headers={**auth, "Idempotency-Key": unique_key("idem_py_create_unknown")},
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

    create_conflict = expect_json(
        "/api/v1/auctions",
        409,
        ok=False,
        code="idempotency_conflict",
        method="POST",
        body=create_body.replace("Python Smoke Lot", "Other Lot"),
        headers=create_headers,
    )
    assert create_conflict["data"] is None

    expect_json("/api/v1/auctions/auc_missing_snapshot", 404, ok=False, code="auction_not_found", headers=auth)
    post_auction_command(
        "/api/v1/auctions/auc_missing_start/start",
        {"expectedRevision": 0},
        auth,
        unique_key("idem_py_start_missing"),
        404,
        False,
        code="auction_not_found",
    )

    snapshot = expect_json(f"/api/v1/auctions/{auction_id}", 200, ok=True, headers=auth)
    assert snapshot["data"]["auction"]["revision"] == 0

    post_auction_command(
        f"/api/v1/auctions/{auction_id}/start",
        {"expectedRevision": 0, "unexpected": True},
        auth,
        unique_key("idem_py_start_unknown"),
        400,
        False,
        code="validation_failed",
    )

    bidder_login = login_as_bidder()
    bidder_auth = {"Authorization": f"Bearer {bidder_login['data']['accessToken']}"}
    bidder_payload = decode_jwt_payload(bidder_login["data"]["accessToken"])
    assert bidder_payload["role"] == "bidder"
    assert bidder_payload["scopes"] == ["auctions:read", "bids:write", "chat:write"]

    post_auction_command(
        "/api/v1/auctions/auc_missing_bid/bids",
        {"amount": 120, "expectedRevision": 0},
        bidder_auth,
        unique_key("idem_py_bid_missing"),
        404,
        False,
        code="auction_not_found",
    )
    expect_json(
        "/api/v1/auctions/auc_missing_events/events",
        404,
        ok=False,
        code="auction_not_found",
        headers=bidder_auth,
    )
    post_auction_command(
        f"/api/v1/auctions/{auction_id}/bids",
        {"amount": 120, "expectedRevision": 0},
        bidder_auth,
        unique_key("idem_py_bid_before_start"),
        409,
        False,
        code="auction_not_running",
    )

    login = login_as_auctioneer()
    auth = {"Authorization": f"Bearer {login['data']['accessToken']}"}

    start_body = {"expectedRevision": 0}
    start_key = unique_key("idem_py_start_flow")
    started = post_auction_command(
        f"/api/v1/auctions/{auction_id}/start",
        start_body,
        auth,
        start_key,
        200,
        True,
    )
    assert started["data"]["auction"]["revision"] == 1

    replayed_start = post_auction_command(
        f"/api/v1/auctions/{auction_id}/start",
        start_body,
        auth,
        start_key,
        200,
        True,
    )
    assert replayed_start["data"]["auction"]["revision"] == 1

    post_auction_command(
        f"/api/v1/auctions/{auction_id}/start",
        {"expectedRevision": 1},
        auth,
        start_key,
        409,
        False,
        code="idempotency_conflict",
    )
    post_auction_command(
        f"/api/v1/auctions/{auction_id}/start",
        {"expectedRevision": 0},
        auth,
        unique_key("idem_py_start_stale"),
        409,
        False,
        code="stale_revision",
    )

    post_auction_command(
        f"/api/v1/auctions/{auction_id}/bids",
        {"amount": 120, "expectedRevision": 1},
        auth,
        unique_key("idem_py_auctioneer_bid_denied"),
        401,
        False,
        code="unauthorized",
    )

    bidder_login = login_as_bidder()
    auth = {"Authorization": f"Bearer {bidder_login['data']['accessToken']}"}

    post_auction_command(
        f"/api/v1/auctions/{auction_id}/bids",
        {"amount": 100, "expectedRevision": 1},
        auth,
        unique_key("idem_py_bid_below_min"),
        409,
        False,
        code="bid_below_minimum",
    )
    post_auction_command(
        f"/api/v1/auctions/{auction_id}/bids",
        {"amount": 1001, "expectedRevision": 1},
        auth,
        unique_key("idem_py_bid_above_max"),
        409,
        False,
        code="amount_too_high",
    )
    post_auction_command(
        f"/api/v1/auctions/{auction_id}/bids",
        {"amount": 120, "expectedRevision": 1, "unexpected": True},
        auth,
        unique_key("idem_py_bid_unknown"),
        400,
        False,
        code="validation_failed",
    )

    bid_body = {"amount": 120, "expectedRevision": 1}
    bid_key = unique_key("idem_py_bid_flow")
    bid = post_auction_command(
        f"/api/v1/auctions/{auction_id}/bids",
        bid_body,
        auth,
        bid_key,
        201,
        True,
    )
    assert bid["data"]["bid"]["accepted"] is True
    assert bid["data"]["auction"]["revision"] == 2

    replayed_bid = post_auction_command(
        f"/api/v1/auctions/{auction_id}/bids",
        bid_body,
        auth,
        bid_key,
        201,
        True,
    )
    assert replayed_bid["data"]["bid"]["bidId"] == bid["data"]["bid"]["bidId"]

    post_auction_command(
        f"/api/v1/auctions/{auction_id}/bids",
        {"amount": 130, "expectedRevision": 1},
        auth,
        bid_key,
        409,
        False,
        code="idempotency_conflict",
    )
    post_auction_command(
        f"/api/v1/auctions/{auction_id}/bids",
        {"amount": 140, "expectedRevision": 1},
        auth,
        unique_key("idem_py_bid_stale"),
        409,
        False,
        code="stale_revision",
    )

    same_bidder_bid = post_auction_command(
        f"/api/v1/auctions/{auction_id}/bids",
        {"amount": 140, "expectedRevision": 2},
        auth,
        unique_key("idem_py_bid_same_bidder"),
        201,
        True,
    )
    assert same_bidder_bid["data"]["bid"]["accepted"] is True
    assert same_bidder_bid["data"]["auction"]["revision"] == 3

    events = expect_json(f"/api/v1/auctions/{auction_id}/events", 200, ok=True, headers=auth)
    assert [event["eventTypeCode"] for event in events["data"]["events"]] == [1, 2, 5, 5]


def test_write_routes_reject_non_json_content_type():
    payload = expect_json(
        "/api/v1/auth/login",
        415,
        ok=False,
        code="unsupported_media_type",
        method="POST",
        body='{"username":"auctioneer","password":"auctioneer-demo-password"}',
        headers={"Content-Type": "text/plain"},
    )
    assert payload["data"] is None


def test_bcrypt_password_limit_rejects_overlong_password():
    payload = expect_json(
        "/api/v1/auth/login",
        401,
        ok=False,
        code="invalid_credentials",
        method="POST",
        body=json.dumps({"username": "auctioneer", "password": "x" * 73}),
    )
    assert payload["data"] is None
