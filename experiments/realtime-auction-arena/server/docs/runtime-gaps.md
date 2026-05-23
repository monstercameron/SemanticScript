# Runtime Gaps

This document separates what the current executable proves from what still
needs language/runtime or server-library work. Auction-specific behavior belongs
in `experiments/realtime-auction-arena/server/src`, not in native runtime code.

## Executable Now

- Native `webServer` on `127.0.0.1:18083`.
- Registered routes for health, readiness, metrics, API index, auth, session,
  auction list/create/snapshot/start/bid/extend/close, JSON event replay,
  bounded audit replay, chat create/delete/report, and routeNotFound API fallback.
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
  accepted-command `audit_events`, bounded JSON event replay with
  `Last-Event-ID`, `?after`, `?limit`, opt-in SSE replay frames with
  `id`/`event`/`data` plus heartbeat output, seeded viewer authorization,
  stable `eventType` text beside numeric event codes, and bounded audit replay
  over persisted `audit_events`.
- SQLite-backed chat create/delete/report flows with idempotency rows,
  moderation persistence, accepted audit rows, and committed chat event rows in
  the auction event stream.
- Python E2E coverage for auth, refresh replay, stale access-token rejection,
  wrong-role bid denial, env-backed JWT signatures, runtime access-token time
  claims, login rate limiting, login audit rows, create/start/bid/extend/close
  idempotency replay and conflict, JSON/SSE event replay, audit rows, and
  idempotency rows.
- Prometheus-style bootstrap metrics, runtime-gap markers, active SSE replay
  gauges, slow-stream drop counters, subscriber queue capacity, and heartbeat
  interval.
- `405 method_not_allowed` envelopes for unsupported methods on known
  executable paths through the native routeMethodNotAllowed fallback.
- Build-time server config defaults in `server/build.sem` plus documented
  deployment config keys for database path, bind address, request limits, rate
  limits, SSE heartbeat, and graceful shutdown.

## Still Missing

- Production auth hardening now fails readiness and login when
  `AUCTION_ARENA_PROFILE=production` and `AUCTION_ARENA_JWT_SECRET` is absent
  or shorter than 32 bytes. Durable multi-session refresh-token/session lookup
  and account-lock policy beyond the seeded disabled-user check remain open.
- Registered create/start/extend/close routes, bid routes, chat routes, event
  replay, admin audit, and metrics enforce the process-local seeded role/scope
  split. Viewer/admin/service guard helpers exist for current and future route
  families.
- Long-lived live SSE fanout still needs route-level fanout,
  request/connection cancellation, per-client queues, and backpressure.
  `/events` is authenticated and authorized bounded JSON replay by default for
  the seeded auctioneer or bidder principals; `Accept: text/event-stream`
  returns executable SSE replay frames with `id`, `event`, `data`, a heartbeat,
  disconnect checks, and active/slow-drop metrics. The contract now fixes
  replay-before-live ordering, 15000 ms heartbeats, 256-item per-client queues,
  disconnect cleanup, and slow-client drop metrics for the future live
  subscription path. `standard.http` now exposes blocking SSE stream primitives
  through runtimeBinding (`openSseStream`, `writeSseEvent`,
  `writeSseEventWithId`, `writeSseHeartbeat`, `closeSseStream`, and
  `clientDisconnected`), while `http.responseSseEvent` remains the one-shot
  frame formatter.
- Full admin policy is executable for bounded audit replay: the route requires
  the seeded admin bearer and rejects valid non-admin callers with
  `insufficient_role`. Audit pagination now uses an opaque
  `(created_at, audit_event_id)` cursor tiebreak, with legacy `?after`
  timestamp input still accepted for compatibility. Broader admin
  user-management routes remain future work.
- Request logging now writes durable finish rows for registered auction command
  accepts and bid rejects, and completed rows normalize zero-duration inputs to
  a positive persisted duration. A reusable request context, true monotonic
  duration source, dynamic request-id generation for every path, start rows,
  and broader runtime-backed counters/gauges remain open.
- Rejected bid audit rows and auth login/refresh/logout/session audit rows are
  durable for executable paths. Broader denied/failed command audit rows remain
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
  finish, closing the listen socket, and returning `SS_HTTP_OK`. `standard.http`
  exposes that drain flag through `serverIsShuttingDown`; this server's
  readiness handler and request middleware use it to return `server_shutting_down`
  for readiness and new POST/DELETE command routes during drain. Production
  cancellation is still incomplete because SemanticScript does not yet expose
  request cancellation tokens or async subscriber drains.

## Graceful Shutdown Plan

The app-level shutdown sequence is:

1. Stop accepting new HTTP requests at the process manager or native server
   boundary.
2. Mark server state as draining so new auth, auction, bid, and chat command
   routes fail with a stable `server_shutting_down` code.
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
process-signal accept-loop shutdown and handler-observable drain state are
executable, but task cancellation and async subscriber drains remain runtime
features.

## Language And Runtime Pressure Points

- Dynamic string building for response envelopes and request ids.
- Typed JWT claim extraction for arbitrary incoming tokens in SemanticScript.
- Middleware-local request context shared across route handlers.
- SQLite transaction helper ergonomics for `BEGIN IMMEDIATE`, rollback guards,
  and commit.
- `standard.event` now provides libuv-backed start/await process queues with
  strict capacity and `queue_full` backpressure, plus local durable streams with
  locked checksummed append logs, torn-tail recovery, and bounded in-memory
  replay. The auction supervisor has executable ordering/backpressure smoke
  coverage. Production route-handler actor-loop wiring, async `select`,
  cancelable timer producers, and fake clocks remain open.
- Long-lived live SSE fanout on top of the new blocking stream primitives:
  client-disconnect-aware cancellation, async subscriber drains, and
  nonblocking per-subscriber writes.
- SemanticScript-visible HTTP request/connection cancellation tokens.
- Structured logging and monotonic time measurement.
- Native HTTP client and async-safe Win32 UI update primitives for the desktop
  client.
