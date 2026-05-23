from __future__ import annotations

import sqlite3
import tempfile
from contextlib import contextmanager
from pathlib import Path


SERVER_ROOT = Path(__file__).resolve().parents[1]
SERVER_SRC = SERVER_ROOT / "src"
SCHEMA_SQL = SERVER_ROOT / "sql" / "schema.sql"


@contextmanager
def arena_db():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "auction_arena.sqlite3"
        conn = sqlite3.connect(db_path)
        try:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.executescript(SCHEMA_SQL.read_text(encoding="utf-8"))
            conn.execute("PRAGMA foreign_keys = ON")
            yield conn
        finally:
            conn.close()


def insert_auction(conn: sqlite3.Connection, auction_id: str, *, status: int = 2) -> None:
    conn.execute(
        """
        INSERT INTO auctions(
          auction_id, seller_user_id, created_by_user_id, status, title,
          description, starting_bid_minor, minimum_increment_minor,
          max_bid_minor, anti_sniping_window_ms, anti_sniping_extension_ms,
          current_bid_minor, revision, event_sequence, created_at, starts_at,
          closes_at, updated_at
        )
        VALUES (?, 'user_auctioneer_001', 'user_auctioneer_001', ?, 'Test',
          'Persistence contract test', 100, 25, 10000, 60000, 30000,
          100, 1, 1, 1000, 1000, 2000, 1000)
        """,
        (auction_id, status),
    )


def insert_event(conn: sqlite3.Connection, auction_id: str, sequence: int, event_id: str) -> None:
    conn.execute(
        """
        INSERT INTO auction_events(
          event_id, auction_id, sequence, auction_revision, schema_version,
          event_type, actor_user_id, request_id, idempotency_key, bid_id,
          payload_json, created_at
        )
        VALUES (?, ?, ?, ?, 1, 5, 'user_bidder_demo', ?, ?, '',
          '{"type":"contract"}', ?)
        """,
        (event_id, auction_id, sequence, sequence, f"req_{event_id}", f"idem_{event_id}", 1000 + sequence),
    )


def expect_integrity_error(fn) -> None:
    try:
        fn()
    except sqlite3.IntegrityError:
        return
    raise AssertionError("expected sqlite3.IntegrityError")


def test_schema_migration_idempotency_and_seed_rows() -> None:
    with arena_db() as conn:
        conn.executescript(SCHEMA_SQL.read_text(encoding="utf-8"))

        assert conn.execute("SELECT current_version FROM schema_versions").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM schema_migrations WHERE version = 1").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM users").fetchone()[0] == 4
        assert conn.execute("SELECT count(*) FROM password_credentials").fetchone()[0] == 4
        assert conn.execute("SELECT disabled FROM users WHERE user_id = 'user_disabled_demo'").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM sqlite_master WHERE name = 'request_log'").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM sqlite_master WHERE name = 'rate_limit_buckets'").fetchone()[0] == 1


def test_event_sequence_uniqueness_per_auction() -> None:
    with arena_db() as conn:
        insert_auction(conn, "auc_sequence")
        insert_event(conn, "auc_sequence", 1, "evt_sequence_1")

        expect_integrity_error(lambda: insert_event(conn, "auc_sequence", 1, "evt_sequence_duplicate"))

        insert_event(conn, "auc_sequence", 2, "evt_sequence_2")
        rows = conn.execute(
            "SELECT sequence FROM auction_events WHERE auction_id = ? ORDER BY sequence",
            ("auc_sequence",),
        ).fetchall()
        assert rows == [(1,), (2,)]


def test_rejected_bid_storage_contract_and_checks() -> None:
    with arena_db() as conn:
        insert_auction(conn, "auc_rejected_bid")
        conn.execute(
            """
            INSERT INTO bids(
              bid_id, auction_id, bidder_user_id, amount_minor, status,
              reject_reason, auction_revision, expected_revision,
              has_expected_revision, request_id, idempotency_key,
              response_status, error_code, created_at
            )
            VALUES ('bid_rejected_1', 'auc_rejected_bid', 'user_bidder_demo',
              110, 2, 4, 1, 0, 1, 'req_rejected_bid',
              'idem_rejected_bid', 400, 'bid_below_minimum', 1200)
            """
        )

        row = conn.execute(
            """
            SELECT bidder_user_id, amount_minor, status, reject_reason,
              auction_revision, expected_revision, request_id, idempotency_key,
              response_status, error_code
            FROM bids WHERE bid_id = 'bid_rejected_1'
            """
        ).fetchone()
        assert row == (
            "user_bidder_demo",
            110,
            2,
            4,
            1,
            0,
            "req_rejected_bid",
            "idem_rejected_bid",
            400,
            "bid_below_minimum",
        )

        expect_integrity_error(
            lambda: conn.execute(
                """
                INSERT INTO bids(
                  bid_id, auction_id, bidder_user_id, amount_minor, status,
                  reject_reason, request_id, idempotency_key, created_at
                )
                VALUES ('bid_invalid_rejected', 'auc_rejected_bid',
                  'user_bidder_demo', 110, 2, 0, 'req_invalid',
                  'idem_invalid', 1300)
                """
            )
        )


def test_command_rollback_preserves_no_partial_domain_rows() -> None:
    with arena_db() as conn:
        try:
            conn.execute("BEGIN IMMEDIATE")
            insert_auction(conn, "auc_rollback")
            insert_event(conn, "auc_rollback", 1, "evt_rollback_1")
            insert_event(conn, "auc_rollback", 1, "evt_rollback_duplicate")
            conn.commit()
            raise AssertionError("duplicate event sequence should have failed")
        except sqlite3.IntegrityError:
            conn.rollback()

        assert conn.execute("SELECT count(*) FROM auctions WHERE auction_id = 'auc_rollback'").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM auction_events WHERE auction_id = 'auc_rollback'").fetchone()[0] == 0


def test_persistence_transaction_helpers_own_handler_boilerplate() -> None:
    persistence_source = (SERVER_SRC / "persistence_tx.sem").read_text(encoding="utf-8")
    sql_query_source = (SERVER_SRC / "sql_queries.sem").read_text(encoding="utf-8")

    assert "operation beginSqliteCommandTransaction" in persistence_source
    assert "operation commitSqliteCommandTransaction" in persistence_source
    assert "operation rollbackSqliteCommandTransaction" in persistence_source
    assert "sql body sqlBeginImmediateCommandTransaction\n  BEGIN IMMEDIATE" in persistence_source
    assert "sql body sqlCommitCommandTransaction\n  COMMIT" in persistence_source
    assert "sql body sqlRollbackCommandTransaction\n  ROLLBACK" in persistence_source

    assert "sqlBeginTransaction" not in sql_query_source
    assert "sqlCommitTransaction" not in sql_query_source
    assert "sqlRollbackTransaction" not in sql_query_source

    for module_name, expected_count in [
        ("auction_context.sem", 6),
        ("chat_context.sem", 5),
        ("auth_context.sem", 2),
    ]:
        source = (SERVER_SRC / module_name).read_text(encoding="utf-8")
        assert "sql.sqlBeginTransaction" not in source
        assert "sql.sqlCommitTransaction" not in source
        assert "sql.sqlRollbackTransaction" not in source
        assert not any(
            line.startswith("defer ") and " sqlite.exec " in line
            for line in source.splitlines()
        )
        assert source.count("tx.beginSqliteCommandTransaction") == expected_count
        assert source.count("tx.commitSqliteCommandTransaction") == expected_count
        assert source.count("defer ") >= expected_count
        assert source.count(" rollbackSqliteCommandTransaction ") == expected_count


def test_scoped_idempotency_uniqueness_and_replace() -> None:
    with arena_db() as conn:
        insert_auction(conn, "auc_idem")
        values = (
            "auction.bid",
            "idem_scope",
            "hash_a",
            "user_bidder_demo",
            "auc_idem",
            202,
            '{"ok":true}',
            1000,
            2000,
        )
        conn.execute(
            """
            INSERT INTO idempotency_keys(
              scope, key, request_hash, actor_user_id, auction_id,
              response_status, response_json, created_at, expires_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            values,
        )

        expect_integrity_error(
            lambda: conn.execute(
                """
                INSERT INTO idempotency_keys(
                  scope, key, request_hash, actor_user_id, auction_id,
                  response_status, response_json, created_at, expires_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                values,
            )
        )

        conn.execute(
            """
            INSERT OR REPLACE INTO idempotency_keys(
              scope, key, request_hash, actor_user_id, auction_id,
              response_status, response_json, created_at, expires_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "auction.bid",
                "idem_scope",
                "hash_b",
                "user_bidder_demo",
                "auc_idem",
                409,
                '{"ok":false}',
                1100,
                2100,
            ),
        )
        row = conn.execute(
            """
            SELECT request_hash, response_status, response_json
            FROM idempotency_keys
            WHERE scope = 'auction.bid' AND key = 'idem_scope'
              AND actor_user_id = 'user_bidder_demo' AND auction_id = 'auc_idem'
            """
        ).fetchone()
        assert row == ("hash_b", 409, '{"ok":false}')


def test_request_log_contract_and_timestamp_checks() -> None:
    with arena_db() as conn:
        conn.execute(
            """
            INSERT INTO request_log(
              request_id, method, path, route_pattern, status, actor_user_id,
              actor_role, duration_ms, auction_id, idempotency_key,
              ip_address_hash, user_agent_hash, request_bytes, response_bytes,
              error_code, started_at, finished_at
            )
            VALUES (
              'req_log_1', 'POST', '/api/v1/auctions/auc_log/bids',
              '/api/v1/auctions/:auctionId/bids', 401, 'user_auctioneer_001',
              20, 7, 'auc_log', 'idem_log', 'sha256:ip', 'sha256:ua',
              44, 123, 'unauthorized', 1000, 1007
            )
            """
        )
        row = conn.execute(
            """
            SELECT route_pattern, status, actor_user_id, actor_role,
              duration_ms, error_code
            FROM request_log WHERE request_id = 'req_log_1'
            """
        ).fetchone()
        assert row == ("/api/v1/auctions/:auctionId/bids", 401, "user_auctioneer_001", 20, 7, "unauthorized")

        expect_integrity_error(
            lambda: conn.execute(
                """
                INSERT INTO request_log(
                  request_id, method, path, route_pattern, status, started_at,
                  finished_at
                )
                VALUES ('req_log_bad_time', 'GET', '/metrics', '/metrics', 200, 2000, 1999)
                """
            )
        )


def test_audit_outcome_contract_and_rejection_checks() -> None:
    with arena_db() as conn:
        for outcome, action, error_code in [
            (1, "auction.create", ""),
            (2, "bid.rejected", "bid_below_minimum"),
            (3, "auction.start", "unauthorized"),
            (4, "auth.login.rejected", "invalid_credentials"),
        ]:
            conn.execute(
                """
                INSERT INTO audit_events(
                  audit_event_id, schema_version, actor_user_id, actor_role,
                  request_id, idempotency_key, action, command_kind, auction_id,
                  bid_id, outcome, error_code, payload_json, created_at
                )
                VALUES (?, 1, 'user_bidder_demo', 10, ?, '', ?, 6, '',
                  '', ?, ?, '{"redacted":true}', ?)
                """,
                (f"aud_{outcome}", f"req_audit_{outcome}", action, outcome, error_code, 1000 + outcome),
            )

        assert conn.execute("SELECT count(*) FROM audit_events").fetchone()[0] == 4
        assert conn.execute("SELECT count(*) FROM audit_events WHERE outcome = 2").fetchone()[0] == 1
        audit_cursor_indexes = {
            row[1] for row in conn.execute("PRAGMA index_list('audit_events')").fetchall()
        }
        assert "idx_audit_auction_cursor" in audit_cursor_indexes

        expect_integrity_error(
            lambda: conn.execute(
                """
                INSERT INTO audit_events(
                  audit_event_id, schema_version, request_id, action, outcome,
                  payload_json, created_at
                )
                VALUES ('aud_bad_outcome', 1, 'req_bad_outcome',
                  'bid.rejected', 0, '{}', 2000)
                """
            )
        )


def test_rate_limit_bucket_contract_and_rollups() -> None:
    with arena_db() as conn:
        conn.execute(
            """
            INSERT INTO rate_limit_buckets(
              bucket_key, scope, actor_user_id, route_pattern, window_start,
              window_ms, count, denied_count, limit_count, reset_at, updated_at
            )
            VALUES (
              'bid:user_bidder_demo:auc_rate:1000', 'auction.bid',
              'user_bidder_demo', '/api/v1/auctions/:auctionId/bids',
              1000, 10000, 21, 1, 20, 11000, 1001
            )
            """
        )
        row = conn.execute(
            """
            SELECT scope, actor_user_id, count, denied_count, limit_count
            FROM rate_limit_buckets
            WHERE bucket_key = 'bid:user_bidder_demo:auc_rate:1000'
            """
        ).fetchone()
        assert row == ("auction.bid", "user_bidder_demo", 21, 1, 20)

        expect_integrity_error(
            lambda: conn.execute(
                """
                INSERT INTO rate_limit_buckets(
                  bucket_key, window_start, window_ms, count, denied_count,
                  limit_count, reset_at
                )
                VALUES ('bad_rate', 1000, 10000, 0, -1, 10, 11000)
                """
            )
        )


def test_observability_metric_rollup_sources() -> None:
    with arena_db() as conn:
        insert_auction(conn, "auc_metrics_draft", status=1)
        insert_auction(conn, "auc_metrics_running", status=2)
        conn.execute(
            """
            INSERT INTO bids(
              bid_id, auction_id, bidder_user_id, amount_minor, status,
              reject_reason, request_id, idempotency_key, created_at
            )
            VALUES ('bid_metric_accepted', 'auc_metrics_running',
              'user_bidder_demo', 150, 1, 0, 'req_metric_a',
              'idem_metric_a', 1000)
            """
        )
        conn.execute(
            """
            INSERT INTO bids(
              bid_id, auction_id, bidder_user_id, amount_minor, status,
              reject_reason, request_id, idempotency_key, response_status,
              error_code, created_at
            )
            VALUES ('bid_metric_rejected', 'auc_metrics_running',
              'user_bidder_demo', 110, 2, 4, 'req_metric_r',
              'idem_metric_r', 400, 'bid_below_minimum', 1001)
            """
        )
        conn.execute(
            """
            INSERT INTO request_log(
              request_id, method, path, route_pattern, status, error_code,
              started_at, finished_at
            )
            VALUES ('req_metric_log', 'POST', '/api/v1/auctions/auc/bids',
              '/api/v1/auctions/:auctionId/bids', 400,
              'bid_below_minimum', 1000, 1001)
            """
        )

        auction_status_counts = dict(conn.execute("SELECT status, count(*) FROM auctions GROUP BY status").fetchall())
        bid_status_counts = dict(conn.execute("SELECT status, count(*) FROM bids GROUP BY status").fetchall())
        rejected_reason_counts = dict(
            conn.execute("SELECT reject_reason, count(*) FROM bids WHERE status = 2 GROUP BY reject_reason").fetchall()
        )
        request_counts = dict(
            conn.execute("SELECT route_pattern || ':' || status, count(*) FROM request_log GROUP BY route_pattern, status").fetchall()
        )

        assert auction_status_counts == {1: 1, 2: 1}
        assert bid_status_counts == {1: 1, 2: 1}
        assert rejected_reason_counts == {4: 1}
        assert request_counts == {"/api/v1/auctions/:auctionId/bids:400": 1}


def main() -> None:
    tests = [
        test_schema_migration_idempotency_and_seed_rows,
        test_event_sequence_uniqueness_per_auction,
        test_rejected_bid_storage_contract_and_checks,
        test_command_rollback_preserves_no_partial_domain_rows,
        test_persistence_transaction_helpers_own_handler_boilerplate,
        test_scoped_idempotency_uniqueness_and_replace,
        test_request_log_contract_and_timestamp_checks,
        test_audit_outcome_contract_and_rejection_checks,
        test_rate_limit_bucket_contract_and_rollups,
        test_observability_metric_rollup_sources,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")


if __name__ == "__main__":
    main()
