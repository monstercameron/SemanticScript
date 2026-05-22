import base64
import json
import os
import urllib.error
import urllib.request


BASE_URL = os.environ.get("AUCTION_ARENA_BASE_URL", "http://127.0.0.1:18083")
REQUEST_ID = "req_python_smoke"


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


def test_health_ready_and_api_envelopes():
    for path in ["/healthz", "/readyz", "/api/v1", "/api/v1/auctions"]:
        expect_json(path, 200, ok=True)


def test_api_index_only_asserts_executable_routes():
    payload = expect_json("/api/v1", 200, ok=True)
    route_text = "\n".join(payload["data"]["routes"])
    assert "POST /api/v1/auth/login" in route_text
    assert "POST /api/v1/auth/refresh" in route_text
    assert "POST /api/v1/auth/logout" in route_text
    assert "GET /api/v1/session" in route_text
    assert "GET /api/v1/auctions" in route_text
    assert "POST /api/v1/auctions" in route_text


def test_metrics_smoke():
    status, headers, text = request("/metrics")
    assert status == 200
    assert_common_headers(headers, "/metrics")
    assert "auction_server_bootstrap_info" in text
    assert 'auction_server_bootstrap_info{api_version="v1",runtime="native_http_exact_routes"} 1' in text
    assert 'auction_server_runtime_gap{feature="long_lived_sse"} 1' in text
    assert 'auction_server_runtime_gap{feature="sqlite_persistence"} 1' in text
    assert 'auction_server_runtime_gap{feature="request_logging_counters"} 1' in text


def test_auth_demo_flow_is_enveloped():
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
    assert "iat" in token_payload
    assert "nbf" in token_payload
    assert token_payload["exp"] == 2000000000
    assert "jti" in token_payload


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


def test_auction_create_fails_closed_until_runtime_writes_exist():
    missing_key = expect_json(
        "/api/v1/auctions",
        400,
        ok=False,
        code="missing_idempotency_key",
        method="POST",
        body="{}",
    )
    assert missing_key["data"] is None

    payload = expect_json(
        "/api/v1/auctions",
        403,
        ok=False,
        code="forbidden",
        method="POST",
        body="{}",
        headers={"Idempotency-Key": "idem_py_create_001"},
    )
    assert payload["data"] is None


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
