# Runtime Gaps

This document separates what the current executable proves from what still
needs language/runtime or server-library work. Auction-specific behavior belongs
in `experiments/realtime-auction-arena/server/src`, not in native runtime code.

## Executable Now

- Native `webServer` on `127.0.0.1:18083`.
- Registered routes for health, readiness, metrics, API index, auth, session,
  auction list/create/snapshot/start/bid/extend/close, JSON event replay,
  bounded audit replay, chat create/delete/report, and explicit API not-found.
- SQLite open and schema initialization from `server/sql/schema.sql` during
  readiness and command handling.
- Stable response headers: `X-Api-Version`, `X-Request-Id`,
  `X-Max-Body-Bytes`, and `X-Route-Path`.
- Guard envelopes for `payload_too_large`, `unsupported_media_type`,
  `missing_idempotency_key`, `idempotency_conflict`, `unauthorized`,
  `auction_not_found`, `stale_revision`, and `auction_not_running`.
- Demo auth flow: JSON login body parsing, bcrypt verification for the seeded
  `auctioneer` and `bidder` accounts, bcrypt 72-byte precheck, opaque
  refresh-token generation, bcrypt-hashed process-local refresh-token storage,
  refresh rotation, logout revocation, current-bearer session lookup, optional
  `AUCTION_ARENA_JWT_SECRET` signing/verification override, runtime
  `iat`/`nbf`/`exp = iat + 900` token issue, stored active-token time
  validation during session lookup, SQLite-backed login rate-limit buckets, and
  durable login accepted/rejected audit rows.
- `standard.jwt` exposes generic HS256 primitives: sign a caller-supplied JSON
  payload template with a generated `jti`, and verify compact JWT signatures.
  The arena issuer, audience, subject, role, and scopes live in
  `server/src/auth_context.sem`.
- SQLite-backed auction create/list/snapshot/start/bid/extend/close flows with
  transaction guards, persisted `auction_events`, scoped `idempotency_keys`,
  accepted-command `audit_events`, bounded JSON event replay with `Last-Event-ID`,
  `?after`, `?limit`, seeded viewer authorization, stable `eventType` text
  beside numeric event codes, and bounded audit replay over persisted
  `audit_events`.
- SQLite-backed chat create/delete/report flows with idempotency rows,
  moderation persistence, accepted audit rows, and committed chat event rows in
  the auction event stream.
- Python E2E coverage for auth, refresh replay, stale access-token rejection,
  wrong-role bid denial, env-backed JWT signatures, runtime access-token time
  claims, login rate limiting, login audit rows, create/start/bid/extend/close
  idempotency replay and conflict, event replay, audit rows, and idempotency
  rows.
- Prometheus-style bootstrap metrics, runtime-gap markers, and zero-valued SSE
  contract gauges/counters for active clients, slow-client drops, subscriber
  queue capacity, and heartbeat interval.
- `405 method_not_allowed` envelopes for unsupported methods on known
  executable paths.
- Build-time server config defaults in `server/build.sem` plus documented
  deployment config keys for database path, bind address, request limits, rate
  limits, SSE heartbeat, and graceful shutdown.

## Still Missing

- Production auth hardening still missing: production mode that makes absent or
  invalid `AUCTION_ARENA_JWT_SECRET` fatal, typed JWT claim extraction for
  arbitrary incoming tokens, JWT denylist persistence/lookup, durable
  refresh-token/session rows, disabled/locked user checks, and
  refresh/logout/session audit rows.
- Registered create/start routes and the bid route enforce the process-local
  seeded role/scope split, but authorization is not enforced from decoded JWT
  principals yet. Viewer, admin, service, and chat policies, plus the `403
  forbidden` split for authenticated-but-unauthorized callers, remain missing.
- Long-lived SSE needs streaming response APIs, heartbeat writes, disconnect
  detection, per-client queues, and backpressure. `/events` is currently
  authenticated and authorized bounded JSON replay for the seeded auctioneer or
  bidder principals; replay cursor, page-size parsing, event ordering, and
  event type naming are executable for the JSON fallback. The contract now fixes
  replay-before-live ordering, 15000 ms heartbeats, 256-item per-client queues,
  disconnect cleanup, and slow-client drop metrics for the future streaming
  path. The native HTTP adapter still has only one-shot response writers:
  `http.responseSseEvent` formats a single `text/event-stream` body, and the
  fallback transport sends `Content-Length` plus `Connection: close`.
- Full admin policy is still missing: the audit replay route is registered and
  executable, but it currently accepts the seeded auctioneer bearer as the demo
  audit operator until a seeded admin principal and decoded-scope authorization
  are executable.
- Request logging now writes durable finish rows for registered auction command
  accepts and bid rejects, but still needs a reusable request context,
  monotonic duration measurement, dynamic request-id generation for every path,
  start rows, and broader runtime-backed counters/gauges.
- Rejected bid audit rows are durable for executable bid rule rejects.
  Denied/failed command audit rows and refresh/logout/session audit rows remain
  planned.
- Idempotency uses the raw request body as the request-hash surrogate. Canonical
  JSON hashing and fully atomic replay lookup plus write under one transaction
  are still needed for concurrent production semantics.
- Typed JSON command parsing still accepts only the fields the handlers read; a
  strict unknown-field validator is still planned.
- Event replay cursor and limit parsing is executable but uses the standard
  decimal-prefix parser; strict rejection of trailing junk and the dedicated
  `replay_cursor_invalid` envelope remain planned.
- The native HTTP fallback server now handles process-level SIGINT/SIGTERM
  shutdown by stopping the accept loop, letting the currently accepted request
  finish, closing the listen socket, and returning `SS_HTTP_OK`. Production
  command-drain behavior is still incomplete because SemanticScript does not yet
  expose source-level cancellation tokens, server drain state, or async
  subscriber drains to handlers.

## Graceful Shutdown Plan

The app-level shutdown sequence is:

1. Stop accepting new HTTP requests at the process manager or native server
   boundary.
2. Mark server state as draining so new auction/chat commands fail with a stable
   `server_shutting_down` code once command queues exist.
3. Let already accepted SQLite command transactions commit or roll back under
   their existing transaction guard.
4. Broadcast only events that committed before the drain marker.
5. Close SSE subscribers with a final heartbeat/error frame when long-lived SSE
   is executable.
6. Flush structured request logs, checkpoint/close SQLite, and exit before the
   grace deadline.

Current executable validation uses the Python E2E/load/demo harnesses: each
starts the local server, completes requests, terminates the process, and then
opens SQLite to verify the database remains readable. The native HTTP adapter's
process-signal accept-loop shutdown is executable, but task cancellation,
handler-observable drain state, and async subscriber drains remain runtime
features.

## Language And Runtime Pressure Points

- Dynamic string building for response envelopes and request ids.
- Typed JWT claim extraction for arbitrary incoming tokens in SemanticScript.
- Middleware-local request context shared across route handlers.
- SQLite transaction helper ergonomics for `BEGIN IMMEDIATE`, rollback guards,
  and commit.
- Async channels, cancelable timers, fake clocks, bounded per-auction command
  queues, and per-auction supervisors.
- Long-lived HTTP response streams for SSE, plus client-disconnect detection
  and nonblocking per-subscriber writes.
- SemanticScript-visible HTTP shutdown/cancellation hooks, including
  handler-observable drain state and a request/connection cancellation token.
- Structured logging and monotonic time measurement.
- Native HTTP client and async-safe Win32 UI update primitives for the desktop
  client.
