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
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
SERVER_DIR = ROOT / "experiments" / "realtime-auction-arena" / "server"
EXE = SERVER_DIR / "build" / "realtime_auction_arena_server.exe"
BASE_URL = os.environ.get("AUCTION_ARENA_BASE_URL", "http://127.0.0.1:18083")


def request(path, method="GET", body=None, headers=None, timeout=5):
    data = None
    merged_headers = {"X-Request-Id": f"req_load_{uuid.uuid4().hex}"}
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


def login(username):
    return expect_json(
        "/api/v1/auth/login",
        200,
        ok=True,
        method="POST",
        body=json.dumps({"username": username, "password": "auctioneer-demo-password"}),
    )


def post_command(path, body, auth, idem):
    return expect_json(
        path,
        201 if path.endswith("/bids") else 200,
        ok=True,
        method="POST",
        body=json.dumps(body, separators=(",", ":")),
        headers={**auth, "Idempotency-Key": idem},
    )


def create_running_auction():
    auctioneer = login("auctioneer")
    auth = {"Authorization": f"Bearer {auctioneer['data']['accessToken']}"}
    body = {
        "title": f"Load Smoke {uuid.uuid4().hex}",
        "description": "Concurrent load smoke lot",
        "startingBid": 100,
        "minimumIncrement": 1,
        "maxBidAmount": 1000000,
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
        body=json.dumps(body, separators=(",", ":")),
        headers={**auth, "Idempotency-Key": f"idem_load_create_{uuid.uuid4().hex}"},
    )
    auction_id = created["data"]["auction"]["auctionId"]
    started = expect_json(
        f"/api/v1/auctions/{auction_id}/start",
        200,
        ok=True,
        method="POST",
        body='{"expectedRevision":0}',
        headers={**auth, "Idempotency-Key": f"idem_load_start_{uuid.uuid4().hex}"},
    )
    assert started["data"]["auction"]["revision"] == 1
    return auction_id


def place_bid(auction_id, auth, amount, expected_revision, prefix):
    return request(
        f"/api/v1/auctions/{auction_id}/bids",
        method="POST",
        body=json.dumps({"amount": amount, "expectedRevision": expected_revision}, separators=(",", ":")),
        headers={**auth, "Idempotency-Key": f"{prefix}_{uuid.uuid4().hex}"},
    )


def run_load(bids, concurrency):
    auction_id = create_running_auction()
    bidder = login("bidder")
    auth = {"Authorization": f"Bearer {bidder['data']['accessToken']}"}

    amount = 101
    revision = 1
    accepted = 0
    for _ in range(bids):
        status, _, text = place_bid(auction_id, auth, amount, revision, "idem_load_bid")
        payload = json.loads(text)
        assert status == 201, f"accepted bid failed: {status} {text}"
        revision = payload["data"]["auction"]["revision"]
        amount += 1
        accepted += 1

    race_expected_revision = revision
    race_amount_start = amount
    race_statuses = []
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [
            pool.submit(
                place_bid,
                auction_id,
                auth,
                race_amount_start + index,
                race_expected_revision,
                "idem_load_race",
            )
            for index in range(concurrency)
        ]
        for future in as_completed(futures):
            status, _, text = future.result()
            race_statuses.append((status, json.loads(text)))

    race_successes = [payload for status, payload in race_statuses if status == 201 and payload["ok"]]
    race_conflicts = [payload for status, payload in race_statuses if status == 409 and not payload["ok"]]
    assert len(race_successes) >= 1, f"expected at least one successful concurrent bid: {race_statuses}"
    assert len(race_successes) + len(race_conflicts) == len(race_statuses), race_statuses
    accepted += len(race_successes)

    events = expect_json(f"/api/v1/auctions/{auction_id}/events", 200, ok=True, headers=auth)
    assert events["data"]["count"] >= accepted + 2

    db_path = SERVER_DIR / "auction_arena.sqlite3"
    with sqlite3.connect(db_path) as conn:
        accepted_rows = conn.execute(
            "SELECT accepted_bid_count FROM auctions WHERE auction_id = ?",
            (auction_id,),
        ).fetchone()[0]
        assert accepted_rows == accepted, (accepted_rows, accepted)

    print(
        json.dumps(
            {
                "auctionId": auction_id,
                "acceptedBids": accepted,
                "raceRequests": len(race_statuses),
                "raceSuccesses": len(race_successes),
                "raceConflicts": len(race_conflicts),
            },
            sort_keys=True,
        )
    )


def main():
    parser = argparse.ArgumentParser(description="Realtime Auction Arena load smoke")
    parser.add_argument("--bids", type=int, default=int(os.environ.get("AUCTION_ARENA_LOAD_BIDS", "10")))
    parser.add_argument("--concurrency", type=int, default=int(os.environ.get("AUCTION_ARENA_LOAD_CONCURRENCY", "6")))
    parser.add_argument("--use-existing", action="store_true", help="use an already running server")
    parser.add_argument("--skip-build", action="store_true", help="skip SemanticScript build before launching")
    args = parser.parse_args()

    if args.bids < 1:
        raise SystemExit("--bids must be >= 1")
    if args.concurrency < 2:
        raise SystemExit("--concurrency must be >= 2")
    if not args.use_existing and not args.skip_build:
        run_build()
    process = start_server(use_existing=args.use_existing)
    try:
        run_load(args.bids, args.concurrency)
    finally:
        stop_server(process)


if __name__ == "__main__":
    main()
