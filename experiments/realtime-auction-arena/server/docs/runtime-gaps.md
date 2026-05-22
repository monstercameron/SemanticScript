# Runtime Gaps

This document separates what the current executable proves from what still
needs language/runtime or server-library work. Auction-specific behavior belongs
in `experiments/realtime-auction-arena/server/src`, not in native runtime code.

## Executable Now

- Native `webServer` on `127.0.0.1:18083`.
- Registered routes for health, readiness, metrics, API index, auth, session,
  auction list/create/snapshot/start/bid, JSON event replay, and explicit API
  not-found.
- SQLite open and schema initialization from `server/sql/schema.sql` during
  readiness and command handling.
- Stable response headers: `X-Api-Version`, `X-Request-Id`,
  `X-Max-Body-Bytes`, and `X-Route-Path`.
- Guard envelopes for `payload_too_large`, `unsupported_media_type`,
  `missing_idempotency_key`, `idempotency_conflict`, `unauthorized`,
  `auction_not_found`, `stale_revision`, and `auction_not_running`.
- Demo auth flow: JSON login body parsing, bcrypt verification for the seeded
  `auctioneer` account, bcrypt 72-byte precheck, opaque refresh-token
  generation, bcrypt-hashed process-local refresh-token storage, refresh
  rotation, logout revocation, and current-bearer session lookup.
- `standard.jwt` exposes generic HS256 primitives: sign a caller-supplied JSON
  payload template with a generated `jti`, and verify compact JWT signatures.
  The arena issuer, audience, subject, role, and scopes live in
  `server/src/main.sem`.
- SQLite-backed auction create/list/snapshot/start/bid flows with transaction
  guards, persisted `auction_events`, scoped `idempotency_keys`, accepted-command
  `audit_events`, and JSON event replay.
- Python E2E coverage for auth, refresh replay, stale access-token rejection,
  create/start/bid idempotency replay and conflict, event replay, audit rows,
  and idempotency rows.
- Prometheus-style bootstrap metrics and runtime-gap markers.

## Still Missing

- Production auth hardening: secret loading from environment/config, runtime
  clock validation for `exp`/`iat`/`nbf`, JWT denylist persistence, durable
  refresh-token/session rows, disabled/locked user checks, and login rate
  limiting.
- Role/scope authorization is not enforced from decoded principals yet. The
  current auction routes require only the active signed bearer token; bid writes
  still attribute to the seeded demo bidder.
- Long-lived SSE needs streaming response APIs, heartbeat writes, disconnect
  detection, per-client queues, backpressure, and replay cursor parsing.
  `/events` is currently authenticated JSON replay.
- Chat, extend, close, audit query, and admin APIs are not registered handlers
  yet.
- Request logging and runtime-backed metrics need a reusable request context,
  monotonic clock reads, dynamic request-id generation, structured log writing,
  and counters/gauges backed by server state.
- Rejected/denied/failed command audit rows are not written yet. The current
  executable writes accepted create/start/bid audit rows only.
- Idempotency uses the raw request body as the request-hash surrogate. Canonical
  JSON hashing and fully atomic replay lookup plus write under one transaction
  are still needed for concurrent production semantics.
- Typed JSON command parsing still accepts only the fields the handlers read; a
  strict unknown-field validator is still planned.
- Method-not-allowed behavior for unsupported methods on known routes is still
  owned by the native dispatcher surface.

## Language And Runtime Pressure Points

- Dynamic string building for response envelopes and request ids.
- Typed JWT claim extraction and validation in SemanticScript.
- Middleware-local request context shared across route handlers.
- SQLite transaction helper ergonomics for `BEGIN IMMEDIATE`, rollback guards,
  and commit.
- Async channels, cancelable timers, fake clocks, and per-auction supervisors.
- Long-lived HTTP response streams for SSE.
- Structured logging and monotonic time measurement.
- Native HTTP client and async-safe Win32 UI update primitives for the desktop
  client.
