PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS schema_versions (
  singleton_id INTEGER PRIMARY KEY CHECK (singleton_id = 1),
  current_version INTEGER NOT NULL,
  applied_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS schema_migrations (
  version INTEGER PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  checksum TEXT NOT NULL,
  applied_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
  user_id TEXT PRIMARY KEY,
  username TEXT NOT NULL,
  username_norm TEXT NOT NULL UNIQUE,
  display_name TEXT NOT NULL,
  role INTEGER NOT NULL,
  status INTEGER NOT NULL,
  disabled INTEGER NOT NULL DEFAULT 0,
  locked_until INTEGER NOT NULL DEFAULT 0,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  CHECK (role IN (10,20,30)),
  CHECK (status IN (1,2,3))
);

CREATE TABLE IF NOT EXISTS password_credentials (
  user_id TEXT PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
  password_hash TEXT NOT NULL,
  cost INTEGER NOT NULL,
  password_updated_at INTEGER NOT NULL,
  failed_login_count INTEGER NOT NULL DEFAULT 0,
  last_failed_login_at INTEGER NOT NULL DEFAULT 0,
  CHECK (cost >= 10)
);

CREATE TABLE IF NOT EXISTS refresh_tokens (
  refresh_token_id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  token_hash TEXT NOT NULL UNIQUE,
  issued_at INTEGER NOT NULL,
  expires_at INTEGER NOT NULL,
  revoked_at INTEGER NOT NULL DEFAULT 0,
  replaced_by_refresh_token_id TEXT UNIQUE,
  created_by_request_id TEXT NOT NULL,
  revoked_by_request_id TEXT NOT NULL DEFAULT '',
  user_agent_hash TEXT NOT NULL DEFAULT '',
  ip_address_hash TEXT NOT NULL DEFAULT '',
  CHECK (expires_at > issued_at)
);

CREATE TABLE IF NOT EXISTS revoked_jwts (
  jti TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  expires_at INTEGER NOT NULL,
  revoked_at INTEGER NOT NULL,
  request_id TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS auctions (
  auction_id TEXT PRIMARY KEY,
  seller_user_id TEXT NOT NULL REFERENCES users(user_id),
  created_by_user_id TEXT NOT NULL REFERENCES users(user_id),
  status INTEGER NOT NULL,
  title TEXT NOT NULL,
  description TEXT NOT NULL,
  starting_bid_minor INTEGER NOT NULL,
  minimum_increment_minor INTEGER NOT NULL,
  max_bid_minor INTEGER NOT NULL,
  anti_sniping_window_ms INTEGER NOT NULL,
  anti_sniping_extension_ms INTEGER NOT NULL,
  current_bid_minor INTEGER NOT NULL,
  current_winner_user_id TEXT NOT NULL DEFAULT '',
  last_bid_id TEXT NOT NULL DEFAULT '',
  last_bidder_user_id TEXT NOT NULL DEFAULT '',
  accepted_bid_count INTEGER NOT NULL DEFAULT 0,
  rejected_bid_count INTEGER NOT NULL DEFAULT 0,
  revision INTEGER NOT NULL DEFAULT 0,
  event_sequence INTEGER NOT NULL DEFAULT 0,
  created_at INTEGER NOT NULL,
  starts_at INTEGER NOT NULL,
  closes_at INTEGER NOT NULL,
  closed_at INTEGER NOT NULL DEFAULT 0,
  updated_at INTEGER NOT NULL,
  CHECK (status IN (1,2,3,4)),
  CHECK (starting_bid_minor >= 0),
  CHECK (minimum_increment_minor > 0),
  CHECK (max_bid_minor > starting_bid_minor),
  CHECK (current_bid_minor >= starting_bid_minor),
  CHECK (revision >= 0),
  CHECK (event_sequence >= 0)
);

CREATE TABLE IF NOT EXISTS bids (
  bid_id TEXT PRIMARY KEY,
  auction_id TEXT NOT NULL REFERENCES auctions(auction_id) ON DELETE CASCADE,
  bidder_user_id TEXT NOT NULL REFERENCES users(user_id),
  amount_minor INTEGER NOT NULL,
  status INTEGER NOT NULL,
  reject_reason INTEGER NOT NULL,
  auction_revision INTEGER NOT NULL DEFAULT 0,
  expected_revision INTEGER NOT NULL DEFAULT 0,
  has_expected_revision INTEGER NOT NULL DEFAULT 0,
  request_id TEXT NOT NULL,
  idempotency_key TEXT NOT NULL,
  response_status INTEGER NOT NULL DEFAULT 0,
  error_code TEXT NOT NULL DEFAULT '',
  created_at INTEGER NOT NULL,
  CHECK (status IN (1,2)),
  CHECK (reject_reason BETWEEN 0 AND 7),
  CHECK (amount_minor >= 0),
  CHECK (auction_revision >= 0),
  CHECK ((status = 1 AND reject_reason = 0) OR (status = 2 AND reject_reason > 0))
);

CREATE TABLE IF NOT EXISTS auction_events (
  event_id TEXT PRIMARY KEY,
  auction_id TEXT NOT NULL REFERENCES auctions(auction_id) ON DELETE CASCADE,
  sequence INTEGER NOT NULL,
  auction_revision INTEGER NOT NULL,
  schema_version INTEGER NOT NULL,
  event_type INTEGER NOT NULL,
  actor_user_id TEXT NOT NULL DEFAULT '',
  request_id TEXT NOT NULL,
  idempotency_key TEXT NOT NULL DEFAULT '',
  bid_id TEXT NOT NULL DEFAULT '',
  chat_message_id TEXT NOT NULL DEFAULT '',
  payload_json TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  UNIQUE(auction_id, sequence),
  CHECK (sequence > 0),
  CHECK (schema_version = 1)
);

CREATE TABLE IF NOT EXISTS chat_messages (
  message_id TEXT PRIMARY KEY,
  auction_id TEXT NOT NULL REFERENCES auctions(auction_id) ON DELETE CASCADE,
  author_user_id TEXT NOT NULL REFERENCES users(user_id),
  status INTEGER NOT NULL,
  body_text TEXT NOT NULL,
  request_id TEXT NOT NULL,
  deleted_at INTEGER NOT NULL DEFAULT 0,
  reported_at INTEGER NOT NULL DEFAULT 0,
  created_at INTEGER NOT NULL,
  CHECK (status IN (1,2,3)),
  CHECK (length(body_text) <= 1000)
);

CREATE TABLE IF NOT EXISTS audit_events (
  audit_event_id TEXT PRIMARY KEY,
  schema_version INTEGER NOT NULL,
  actor_user_id TEXT NOT NULL DEFAULT '',
  actor_role INTEGER NOT NULL DEFAULT 0,
  request_id TEXT NOT NULL,
  idempotency_key TEXT NOT NULL DEFAULT '',
  action TEXT NOT NULL,
  command_kind INTEGER NOT NULL DEFAULT 0,
  auction_id TEXT NOT NULL DEFAULT '',
  bid_id TEXT NOT NULL DEFAULT '',
  outcome INTEGER NOT NULL,
  error_code TEXT NOT NULL DEFAULT '',
  payload_json TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  CHECK (schema_version = 1),
  CHECK (outcome IN (1,2,3,4))
);

CREATE TABLE IF NOT EXISTS request_log (
  request_id TEXT PRIMARY KEY,
  method TEXT NOT NULL,
  path TEXT NOT NULL,
  route_pattern TEXT NOT NULL,
  status INTEGER NOT NULL,
  actor_user_id TEXT NOT NULL DEFAULT '',
  actor_role INTEGER NOT NULL DEFAULT 0,
  duration_ms INTEGER NOT NULL DEFAULT 0,
  auction_id TEXT NOT NULL DEFAULT '',
  idempotency_key TEXT NOT NULL DEFAULT '',
  ip_address_hash TEXT NOT NULL DEFAULT '',
  user_agent_hash TEXT NOT NULL DEFAULT '',
  request_bytes INTEGER NOT NULL DEFAULT 0,
  response_bytes INTEGER NOT NULL DEFAULT 0,
  error_code TEXT NOT NULL DEFAULT '',
  started_at INTEGER NOT NULL,
  finished_at INTEGER NOT NULL DEFAULT 0,
  CHECK (status >= 0),
  CHECK (duration_ms >= 0),
  CHECK (request_bytes >= 0),
  CHECK (response_bytes >= 0),
  CHECK (finished_at = 0 OR finished_at >= started_at)
);

CREATE TABLE IF NOT EXISTS idempotency_keys (
  scope TEXT NOT NULL,
  key TEXT NOT NULL,
  request_hash TEXT NOT NULL,
  request_hash_algorithm TEXT NOT NULL DEFAULT 'raw-body-v1',
  canonical_request_hash TEXT NOT NULL DEFAULT '',
  canonical_request_hash_algorithm TEXT NOT NULL DEFAULT '',
  actor_user_id TEXT NOT NULL DEFAULT '',
  auction_id TEXT NOT NULL DEFAULT '',
  response_status INTEGER NOT NULL,
  response_json TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  expires_at INTEGER NOT NULL,
  PRIMARY KEY(scope, key, actor_user_id, auction_id),
  CHECK (response_status >= 100),
  CHECK (expires_at > created_at)
);

CREATE TABLE IF NOT EXISTS rate_limit_buckets (
  bucket_key TEXT NOT NULL,
  scope TEXT NOT NULL DEFAULT '',
  actor_user_id TEXT NOT NULL DEFAULT '',
  route_pattern TEXT NOT NULL DEFAULT '',
  window_start INTEGER NOT NULL,
  window_ms INTEGER NOT NULL,
  count INTEGER NOT NULL,
  denied_count INTEGER NOT NULL DEFAULT 0,
  limit_count INTEGER NOT NULL,
  reset_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY(bucket_key, window_start),
  CHECK (window_ms > 0),
  CHECK (count >= 0),
  CHECK (denied_count >= 0),
  CHECK (limit_count > 0),
  CHECK (reset_at >= window_start)
);

CREATE INDEX IF NOT EXISTS idx_users_role_status ON users(role, status);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user_expiry ON refresh_tokens(user_id, expires_at, revoked_at);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_replaced_by ON refresh_tokens(replaced_by_refresh_token_id);
CREATE INDEX IF NOT EXISTS idx_revoked_jwts_expiry ON revoked_jwts(expires_at);
CREATE INDEX IF NOT EXISTS idx_auctions_status_closes ON auctions(status, closes_at);
CREATE INDEX IF NOT EXISTS idx_auctions_seller_status ON auctions(seller_user_id, status);
CREATE INDEX IF NOT EXISTS idx_auction_events_replay ON auction_events(auction_id, sequence);
CREATE INDEX IF NOT EXISTS idx_auction_events_time ON auction_events(created_at, event_id);
CREATE INDEX IF NOT EXISTS idx_bids_history ON bids(auction_id, created_at);
CREATE INDEX IF NOT EXISTS idx_bids_bidder_time ON bids(bidder_user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_bids_rejected_reason ON bids(auction_id, reject_reason, created_at)
WHERE status = 2;
CREATE INDEX IF NOT EXISTS idx_chat_messages_auction_time ON chat_messages(auction_id, created_at);
CREATE INDEX IF NOT EXISTS idx_idempotency_expiry ON idempotency_keys(expires_at);
CREATE INDEX IF NOT EXISTS idx_idempotency_scope_actor_auction_expiry
ON idempotency_keys(scope, actor_user_id, auction_id, expires_at);
CREATE INDEX IF NOT EXISTS idx_audit_request ON audit_events(request_id);
CREATE INDEX IF NOT EXISTS idx_audit_actor_time ON audit_events(actor_user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_audit_auction_time ON audit_events(auction_id, created_at);
CREATE INDEX IF NOT EXISTS idx_audit_action_outcome_time ON audit_events(action, outcome, created_at);
CREATE INDEX IF NOT EXISTS idx_audit_bid_time ON audit_events(bid_id, created_at);
CREATE INDEX IF NOT EXISTS idx_request_log_route_status_time ON request_log(route_pattern, status, started_at);
CREATE INDEX IF NOT EXISTS idx_request_log_actor_time ON request_log(actor_user_id, started_at);
CREATE INDEX IF NOT EXISTS idx_request_log_auction_time ON request_log(auction_id, started_at);
CREATE INDEX IF NOT EXISTS idx_request_log_error_time ON request_log(error_code, started_at);
CREATE INDEX IF NOT EXISTS idx_rate_limit_reset ON rate_limit_buckets(reset_at);
CREATE INDEX IF NOT EXISTS idx_rate_limit_actor_scope ON rate_limit_buckets(actor_user_id, scope, reset_at);

INSERT OR IGNORE INTO schema_versions(singleton_id, current_version, applied_at)
VALUES (1, 1, 0);

INSERT OR IGNORE INTO schema_migrations(version, name, checksum, applied_at)
VALUES (1, '001_realtime_auction_arena_persistence', 'schema-v1-static-contract', 0);

INSERT OR IGNORE INTO users(user_id, username, username_norm, display_name, role, status, created_at, updated_at)
VALUES ('user_auctioneer_001', 'auctioneer', 'auctioneer', 'Demo Auctioneer', 20, 1, 0, 0);

INSERT OR IGNORE INTO users(user_id, username, username_norm, display_name, role, status, created_at, updated_at)
VALUES ('user_bidder_demo', 'bidder', 'bidder', 'Demo Bidder', 10, 1, 0, 0);

INSERT OR IGNORE INTO password_credentials(user_id, password_hash, cost, password_updated_at)
VALUES ('user_auctioneer_001', '$2b$12$spS9g0nnkiKOYi.lPsq4duqGlWsYUn8IYZWhgGeJRLskqmwJCsIhi', 12, 0);

INSERT OR IGNORE INTO password_credentials(user_id, password_hash, cost, password_updated_at)
VALUES ('user_bidder_demo', '$2b$12$spS9g0nnkiKOYi.lPsq4duqGlWsYUn8IYZWhgGeJRLskqmwJCsIhi', 12, 0);
