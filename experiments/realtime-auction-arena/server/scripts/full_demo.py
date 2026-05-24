import argparse
import json
import os
import socket
import sqlite3
import subprocess
import sys
import time
import uuid
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
SERVER_DIR = ROOT / "experiments" / "realtime-auction-arena" / "server"
EXE = SERVER_DIR / "build" / "realtime_auction_arena_server.exe"
BASE_URL = os.environ.get("AUCTION_ARENA_BASE_URL", "http://127.0.0.1:18083")


def request(path, method="GET", body=None, headers=None, timeout=5):
    data = None
    merged_headers = {"X-Request-Id": f"req_demo_{uuid.uuid4().hex}"}
    if headers:
        merged_headers.update(headers)
    if body is not None:
        data = body.encode("utf-8")
        merged_headers.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(BASE_URL + path, data=data, headers=merged_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.status, dict(response.headers), response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), exc.read().decode("utf-8")


def expect_json(path, status, ok=None, code=None, method="GET", body=None, headers=None):
    actual_status, _, text = request(path, method=method, body=body, headers=headers)
    payload = json.loads(text)
    assert actual_status == status, f"{method} {path}: expected {status}, got {actual_status}: {text}"
    assert payload["apiVersion"] == "v1"
    if ok is not None:
        assert payload["ok"] is ok, payload
    if code is not None:
        assert payload["error"]["code"] == code, payload
    return payload


def run_build():
    subprocess.run(
        [sys.executable, "SemanticScript/tools/sem.py", "build", "experiments/realtime-auction-arena/server"],
        cwd=ROOT,
        check=True,
    )


def port_is_open(host="127.0.0.1", port=18083):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        return sock.connect_ex((host, port)) == 0


def clean_database():
    for suffix in ["", "-wal", "-shm"]:
        db_path = SERVER_DIR / f"auction_arena.sqlite3{suffix}"
        if db_path.exists():
            try:
                db_path.unlink()
            except FileNotFoundError:
                pass


def start_server(use_existing=False):
    if use_existing:
        status, _, _ = request("/healthz", timeout=2)
        assert status == 200, "existing server did not answer /healthz"
        return None
    if port_is_open():
        raise RuntimeError("port 18083 is already in use; set --use-existing or stop that process")
    clean_database()
    kwargs = {"cwd": SERVER_DIR, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
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
    raise RuntimeError("server did not become ready")


def stop_server(process):
    if process and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)


def seed_admin_contract_row():
    db_path = SERVER_DIR / "auction_arena.sqlite3"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO users(user_id, username, username_norm, display_name, role, status, created_at, updated_at)
            VALUES ('user_admin_demo', 'admin', 'admin', 'Demo Admin', 30, 1, 0, 0)
            """
        )
        conn.commit()


def login(username):
    return expect_json(
        "/api/v1/auth/login",
        200,
        ok=True,
        method="POST",
        body=json.dumps({"username": username, "password": "auctioneer-demo-password"}),
    )


def run_demo(require_full=False):
    expect_json("/readyz", 200, ok=True)
    seed_admin_contract_row()

    auctioneer = login("auctioneer")
    auctioneer_auth = {"Authorization": f"Bearer {auctioneer['data']['accessToken']}"}
    create_body = {
        "title": "Demo Console Lot",
        "description": "Scripted current-capability auction demo",
        "startingBid": 100,
        "minimumIncrement": 10,
        "maxBidAmount": 10000,
        "startsAtUtcMillis": 1,
        "closesAtUtcMillis": 999999999999,
        "antiSnipingWindowMillis": 60000,
        "antiSnipingExtensionMillis": 60000,
    }
    created = expect_json(
        "/api/v1/auctions",
        201,
        ok=True,
        method="POST",
        body=json.dumps(create_body, separators=(",", ":")),
        headers={**auctioneer_auth, "Idempotency-Key": f"idem_demo_create_{uuid.uuid4().hex}"},
    )
    auction_id = created["data"]["auction"]["auctionId"]
    started = expect_json(
        f"/api/v1/auctions/{auction_id}/start",
        200,
        ok=True,
        method="POST",
        body='{"expectedRevision":0}',
        headers={**auctioneer_auth, "Idempotency-Key": f"idem_demo_start_{uuid.uuid4().hex}"},
    )
    assert started["data"]["auction"]["revision"] == 1

    bidder = login("bidder")
    bidder_auth = {"Authorization": f"Bearer {bidder['data']['accessToken']}"}
    revision = 1
    for index, amount in enumerate([120, 140, 170], start=1):
        bid = expect_json(
            f"/api/v1/auctions/{auction_id}/bids",
            201,
            ok=True,
            method="POST",
            body=json.dumps({"amount": amount, "expectedRevision": revision}, separators=(",", ":")),
            headers={**bidder_auth, "Idempotency-Key": f"idem_demo_bid_{index}_{uuid.uuid4().hex}"},
        )
        revision = bid["data"]["auction"]["revision"]

    chat = expect_json(
        f"/api/v1/auctions/{auction_id}/chat/messages",
        201,
        ok=True,
        method="POST",
        body=json.dumps({"text": "demo chat"}, separators=(",", ":")),
        headers={**bidder_auth, "Idempotency-Key": f"idem_demo_chat_{uuid.uuid4().hex}"},
    )
    assert chat["data"]["message"]["status"] == "created"

    auctioneer = login("auctioneer")
    auctioneer_auth = {"Authorization": f"Bearer {auctioneer['data']['accessToken']}"}
    closed = expect_json(
        f"/api/v1/auctions/{auction_id}/close",
        200,
        ok=True,
        method="POST",
        body=json.dumps({"expectedRevision": revision}, separators=(",", ":")),
        headers={**auctioneer_auth, "Idempotency-Key": f"idem_demo_close_{uuid.uuid4().hex}"},
    )
    assert closed["data"]["auction"]["status"] == "closed"

    events = expect_json(f"/api/v1/auctions/{auction_id}/events", 200, ok=True, headers=auctioneer_auth)
    assert events["data"]["count"] == 7
    assert [event["eventTypeCode"] for event in events["data"]["events"]] == [1, 2, 5, 5, 5, 8, 4]

    with sqlite3.connect(SERVER_DIR / "auction_arena.sqlite3") as conn:
        admin = conn.execute("SELECT role FROM users WHERE user_id = 'user_admin_demo'").fetchone()
        assert admin == (30,)
        chat_count = conn.execute(
            "SELECT count(*) FROM chat_messages WHERE auction_id = ? AND body_text = 'demo chat'",
            (auction_id,),
        ).fetchone()[0]
        assert chat_count == 1
        chat_event_count = conn.execute(
            "SELECT count(*) FROM auction_events WHERE auction_id = ? AND event_type = 8 AND chat_message_id <> ''",
            (auction_id,),
        ).fetchone()[0]
        assert chat_event_count == 1
        audit_count = conn.execute(
            "SELECT count(*) FROM audit_events WHERE auction_id = ?",
            (auction_id,),
        ).fetchone()[0]
        assert audit_count >= 6

    if require_full:
        assert events["data"]["count"] == 7

    print(
        json.dumps(
            {
                "auctionId": auction_id,
                "events": events["data"]["count"],
                "chatMessages": 1,
                "adminSeeded": True,
                "blockedSteps": [],
            },
            sort_keys=True,
        )
    )


def main():
    parser = argparse.ArgumentParser(description="Realtime Auction Arena scripted demo")
    parser.add_argument("--use-existing", action="store_true", help="use an already running server")
    parser.add_argument("--skip-build", action="store_true", help="skip SemanticScript build before launching")
    parser.add_argument("--require-full", action="store_true", help="fail unless the complete scripted server demo passes")
    args = parser.parse_args()
    if not args.use_existing and not args.skip_build:
        run_build()
    process = start_server(use_existing=args.use_existing)
    try:
        run_demo(require_full=args.require_full)
    finally:
        stop_server(process)


if __name__ == "__main__":
    main()
