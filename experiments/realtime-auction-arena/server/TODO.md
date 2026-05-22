# Realtime Auction Arena Server TODO

This checklist is server-only. Browser and Win32 work belongs to the sibling
project TODO files. A checkbox means the server behavior or artifact is working
and has a named validation path; contract-only work stays unchecked unless the
task explicitly says "contract".

Current server status: the native API shell builds and runs, health/readiness,
metrics, API index, empty auction listing, stable envelopes, request-id echo,
common runtime headers, 404 envelope, bcrypt-backed demo login, HS256 bearer
session success with required static claim checks, bad-signature rejection,
stale-token rejection after refresh, refresh-token rotation, refresh replay
rejection, logout revocation, post-logout unauthorized session response,
bcrypt's 72-byte password guard, unsupported media-type `415` responses,
oversized-body `413` responses, idempotency-key presence on command writes,
fail-closed auction writes, and bootstrap/runtime-gap metrics are verified by
the Python API harnesses. Production secret loading, durable hashed
refresh-token persistence, SQLite runtime integration, auction mutation
handlers, SSE replay, chat routes, request logging, audit writes, and
runtime-backed metrics are not working yet.

## Verified Working Runtime

- [x] Build the native web server executable with
      `python SemanticScript/tools/sem.py build experiments/realtime-auction-arena/server`.
- [x] Start the built executable on `127.0.0.1:18083` from the E2E harness.
- [x] Serve `GET /healthz` with status `200`, `apiVersion: v1`, `ok: true`,
      and echoed `X-Request-Id`.
- [x] Serve `GET /readyz` with status `200`, `apiVersion: v1`, `ok: true`,
      and echoed `X-Request-Id`.
- [x] Serve `GET /metrics` with Prometheus-style bootstrap metrics text.
- [x] Expose bootstrap/runtime-gap metric series for exact-route native HTTP,
      missing SSE, missing SQLite persistence, and missing request counters.
- [x] Serve `GET /api/v1` with versioned route metadata.
- [x] Serve `GET /api/v1/auctions` with a versioned empty-list scaffold.
- [x] Serve unknown API routes as status `404` with stable error code
      `not_found`.
- [x] Attach `X-Api-Version`, `X-Request-Id`, `X-Max-Body-Bytes`, and
      `X-Route-Path` headers on verified API responses.
- [x] Serve `GET /api/v1/session` as status `401` with stable error code
      `unauthorized` before login and after logout.
- [x] Serve `GET /api/v1/session` as status `200` with seeded auctioneer
      principal data when the active bearer token is supplied.
- [x] Serve `POST /api/v1/auctions` as status `403` with stable error code
      `forbidden` after the required `Idempotency-Key` header is present,
      until roles and transactional writes are implemented.
- [x] Serve command writes missing `Idempotency-Key` as status `400` with
      stable error code `missing_idempotency_key`.
- [x] Serve `POST /api/v1/auth/login` as status `401` with stable error code
      `invalid_credentials` for bad credentials.
- [x] Serve JSON write routes with non-JSON `Content-Type` as status `415`
      with stable error code `unsupported_media_type`.
- [x] Serve `POST /api/v1/auth/login` as status `200` for the seeded
      `auctioneer` account after bcrypt verification.
- [x] Serve `POST /api/v1/auth/refresh` as status `200` for the current
      refresh token, rotate both tokens, and reject refresh replay.
- [x] Serve `POST /api/v1/auth/logout` as status `200` for the current refresh
      token and revoke the process-local demo session.
- [x] E2E probe starts, tests, and shuts down the server through
      `python experiments/realtime-auction-arena/server/tests/e2e_api_smoke.py`.
- [x] Serve oversized `POST /api/v1/auth/login` bodies as status `413` with
      stable error code `payload_too_large`.
- [x] Reject login passwords longer than bcrypt's 72-byte input boundary.
- [x] Assert issued access JWTs include issuer, audience, subject, role,
      scopes, expiration, issued-at, not-before, and token id claims.

## Verified Server Contracts

- [x] Register and build the route shell, response constants, route index,
      auth contract, middleware contract, persistence schema contract,
      auction event contract, auction supervisor contract, chat contract,
      model contract, and auction rule contract from `build.sem`.
- [x] Parse/lint every server `*.test.sem` coverage marker.
- [x] Define versioned API envelopes and stable error payload shapes.
- [x] Define durable model shapes for users, credentials, refresh tokens,
      auctions, bids, events, chat, audit events, request logs, idempotency
      keys, and rate-limit buckets.
- [x] Define deterministic auction rule helper contracts for policy validation,
      lifecycle transitions, bid rejection reasons, anti-sniping extension, and
      winner selection.
- [x] Define SQLite schema text for auth, auctions, bids, events, chat, audit,
      request logs, idempotency, and rate-limit state.
- [x] Define runtime-gap docs for imported JSON constants, body-size handling,
      JWT hardening, bcrypt adapter wiring, SSE, async select/channels, SQLite
      startup initialization, structured logging, and dynamic handler wiring.
- [x] Define an external Python API smoke harness for live HTTP probes.

## P0 - Make Auth Actually Work

- [x] Add a real bcrypt adapter or stdlib binding used by the server runtime.
- [x] Enforce bcrypt's 72-byte password input limit in the live login path.
- [x] Add base64url encode support for token material.
- [x] Add HMAC-SHA256 JWT signing/verification support.
- [x] Add secure random bytes for JWT `jti` values and refresh tokens.
- [ ] Load JWT signing secrets from environment or config, never source.
- [x] Create a deterministic local seeded auctioneer flow for development.
- [x] Implement `POST /api/v1/auth/login`.
- [x] Parse and validate login JSON for the seeded executable path.
- [x] Verify bcrypt password hashes.
- [ ] Rate-limit login attempts.
- [x] Issue access JWTs with issuer, audience, subject, role, scopes,
      expiration, issued-at, not-before, and token id claims.
- [ ] Replace the fixed demo expiration with `now + 900s` and validate `exp`,
      `iat`, and `nbf` against runtime time.
- [x] Issue opaque refresh tokens and store only hashed refresh-token material
      in process-local demo state.
- [ ] Append durable login success/failure audit events.
- [x] Implement `POST /api/v1/auth/refresh` for the process-local demo token.
- [x] Verify refresh token hash and session state.
- [x] Rotate refresh tokens on every use.
- [x] Revoke old refresh tokens.
- [x] Implement `POST /api/v1/auth/logout` for the process-local demo token.
- [x] Revoke process-local demo session state.
- [ ] Optionally denylist active JWT ids until expiration.
- [x] Implement authenticated `GET /api/v1/session` for the active bearer
      token.
- [ ] Protect auctioneer/admin routes by role and scope.
- [ ] Protect bidder bid/chat routes by role and scope.
- [x] Add live API tests for bad JWT signature, stale access token, and refresh
      replay.
- [ ] Add live API tests for disabled user, expired token, wrong audience, and
      insufficient role.
- [x] Add live API tests for bad password, successful login, bearer session,
      refresh, logout, and post-logout unauthorized session.

## P0 - Make Persistence Actually Work

- [ ] Add a SQLite runtime adapter or FFI layer usable by the web server target.
- [ ] Add migration runner or explicit schema initialization.
- [ ] Make `/readyz` fail when schema initialization or validation fails.
- [ ] Add transaction helper for command handlers.
- [ ] Ensure every command write commits auction state, events, audit, request
      log, and idempotency state atomically.
- [ ] Broadcast events only after commit.
- [ ] Roll back state and return stable errors on command failure.
- [ ] Persist rejected bids with reason, actor, amount, auction revision, and
      request id.
- [ ] Persist request logs with request id, route, status, actor, duration, and
      stable error code.
- [ ] Add persistence tests for migration idempotency, event sequence
      uniqueness, idempotency replay, rejected bid storage, and rollback.

## P0 - Make Auction APIs Actually Work

- [ ] Wire route-param extraction into auction/chat handlers for `:auctionId`.
- [ ] Add query parsing for pagination and SSE replay cursors.
- [ ] Add typed JSON body parsing with strict unknown-field handling.
- [ ] Add content-type validation for JSON write routes.
- [ ] Generate a request id when `X-Request-Id` is absent and reflect it in
      headers and envelope bodies.
- [ ] Add method-not-allowed responses for unsupported methods on known paths.
- [x] Add clean body-size limit enforcement returning `413 payload_too_large`
      with common API headers and envelope body.
- [ ] Implement `POST /api/v1/auctions`.
- [ ] Implement `GET /api/v1/auctions/:auctionId`.
- [ ] Implement `POST /api/v1/auctions/:auctionId/start`.
- [ ] Implement `POST /api/v1/auctions/:auctionId/extend`.
- [ ] Implement `POST /api/v1/auctions/:auctionId/close`.
- [ ] Implement `POST /api/v1/auctions/:auctionId/bids`.
- [x] Require idempotency keys for currently registered command write routes.
- [ ] Require idempotency keys for all future auction/chat command routes.
- [ ] Return cached command response for repeated idempotency keys.
- [ ] Return stable rule-failure error codes for bid and lifecycle rejects.
- [ ] Add API integration tests for successful auction lifecycle, unauthorized
      requests, forbidden role requests, idempotency replay, stale revision, and
      every bid reject reason.

## P1 - Async Supervisor And Timers

- [ ] Implement per-auction supervisor loop or the closest runtime-supported
      equivalent.
- [ ] Receive create/start/bid/extend/close commands through bounded queues.
- [ ] Receive timer expiration and shutdown/cancellation events.
- [ ] Add deterministic ordering for simultaneous bids and timer expiry.
- [ ] Add backpressure behavior for saturated command queues.
- [ ] Add fake-clock tests for anti-sniping and close timers.
- [ ] Add async `select`, bounded channels, cancelable timers, and fake clock to
      the language/runtime if they are still missing.

## P1 - SSE Streaming And Replay

- [ ] Implement `GET /api/v1/auctions/:auctionId/events`.
- [ ] Authenticate and authorize SSE subscribers.
- [ ] Support `Last-Event-ID` and `?after=<eventId>` replay.
- [ ] Replay missed events from SQLite before live subscription.
- [ ] Emit heartbeat events.
- [ ] Detect disconnects and remove clients.
- [ ] Add per-client bounded queues.
- [ ] Drop slow clients after queue overflow and count the drop in metrics.
- [ ] Add multi-client broadcast, reconnect, replay-after-event, heartbeat, and
      slow-client tests.
- [ ] Add runtime SSE APIs if still missing:
      `http.sseOpen`, `http.sseWriteEvent`, `http.sseHeartbeat`,
      `http.sseClose`, and `http.clientDisconnected`.

## P1 - Auction Floor Chat

- [ ] Implement `POST /api/v1/auctions/:auctionId/chat/messages`.
- [ ] Implement `DELETE /api/v1/auctions/:auctionId/chat/messages/:messageId`.
- [ ] Implement
      `POST /api/v1/auctions/:auctionId/chat/messages/:messageId/report`.
- [ ] Require bidder role for posting.
- [ ] Require auctioneer/admin role for moderation.
- [ ] Rate-limit chat messages.
- [ ] Enforce max message byte length.
- [ ] Sanitize/escape text before browser rendering.
- [ ] Persist chat messages and moderation events.
- [ ] Emit `chat.message.created`, `chat.message.deleted`, and
      `chat.message.reported` events through the auction event stream.
- [ ] Ensure chat does not change `AuctionState.revision`.
- [ ] Ensure chat participates in replay ordering through event sequence.
- [ ] Keep real HTTP/2 or WebSocket chat as a later transport experiment after
      the SSE path is working.

## P1 - Observability And Security

- [ ] Log request start and finish.
- [ ] Include request id, route pattern, status, actor id, duration, and error
      code in logs.
- [ ] Redact JWTs, refresh tokens, passwords, and raw auth headers in live logs.
- [ ] Audit accepted, rejected, denied, and failed command outcomes.
- [ ] Hash or redact IP and user-agent fields before durable storage.
- [ ] Expand `/metrics` to include active SSE clients, total bids, accepted
      bids, rejected bids by reason, chat accepted/rejected, auction counts by
      status, request counts by route/status, command latency, broadcast
      failures, login failures, and rate-limit hits.
- [ ] Replace bootstrap/runtime-gap metric markers with runtime-backed counters
      and gauges as each persistence, SSE, auth, and command subsystem becomes
      executable.
- [ ] Define allowed CORS origins.
- [ ] Reject unsupported HTTP methods.
- [ ] Reject unknown JSON fields where strict request models require it.
- [ ] Add login, bid, and chat rate limiters.
- [ ] Add CSRF plan before any cookie-authenticated writes.
- [ ] Add metrics and audit tests for auth and command routes.

## P2 - Enterprise Hardening

- [ ] Add OpenAPI-like route contract or generated endpoint index.
- [ ] Add stable error-code registry.
- [ ] Add request/response examples for every route.
- [ ] Add API version compatibility notes and future `/api/v2` deprecation
      plan.
- [ ] Add event schema compatibility notes.
- [ ] Add admin audit query filters.
- [ ] Add pagination for auctions, bids, audit, and events.
- [ ] Add server config file or build tape settings.
- [ ] Add graceful shutdown.
- [ ] Add database backup/export plan.
- [ ] Add local development seed data.
- [ ] Add load smoke for many bids and concurrent bidders.
- [ ] Add full demo script: start server, initialize schema, seed admin, login,
      create auction, start auction, connect browser bidders, submit bids, send
      chat messages, close auction, and verify audit/events.
