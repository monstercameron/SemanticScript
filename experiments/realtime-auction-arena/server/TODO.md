# Realtime Auction Arena Server TODO

This checklist is server-only. Browser and Win32 work belongs to the sibling
project TODO files. A checkbox means the server behavior or artifact is working
and has a named validation path; contract-only work stays unchecked unless the
task explicitly says "contract".

Current server status: the native API shell builds and runs, health/readiness,
metrics, API index, authenticated auction listing, stable envelopes, request-id
echo, common runtime headers, 404 envelope, bcrypt-backed demo login, HS256
bearer issuance from app-owned static claims, signature verification,
active-token session success, bad-signature rejection, stale-token rejection
after refresh, refresh-token rotation, refresh
replay rejection, logout revocation, post-logout unauthorized session response,
bcrypt's 72-byte password guard, unsupported media-type `415` responses,
unsupported-method `405` responses for known paths, oversized-body `413`
responses, SQLite schema initialization, persisted auction
create/list/snapshot/start/bid/extend/close flows, command idempotency replay
and conflict handling, role/scope guards for registered auctioneer and bidder
write routes, local development seed data, accepted-command audit rows, and
bounded JSON event replay are verified by the Python API harnesses. Production
secret override loading, access-token runtime `iat`/`nbf`/`exp` issue and
session validation, login rate limiting, durable login auth audit rows,
runtime-backed request/command metrics, request-log rows, chat-create/delete/report
persistence, bounded audit replay, and the scripted full demo are now wired.
Auth hardening now includes disabled-user rejection, typed access-token
`aud`/`exp`/`jti` checks, JWT denylist lookup, seeded admin audit access, and
`403 insufficient_role` splitting. Audit replay now supports opaque
`createdAtUtcMillis:auditEventId` cursor pagination with an audit id tiebreak.
Source-health cleanup, restart-safe durable session lookup, canonical
idempotency hashing, reusable request-start context, non-SSE shutdown
cancellation, and long-lived live SSE fanout remain open.

Agent loop note: use `sem check --json experiments/realtime-auction-arena/server`
for source-health signal, use
`sem test --json --allow-red-preflight-harnesses experiments/realtime-auction-arena/server`
for runtime-harness signal while source diagnostics remain red, and treat
`sem dev --json` as a watch-plan surface that now separates `buildableSource`
from `sourceOk`; the server can restart while the semantic quality lane remains
red.

## Verified Working Runtime

- [x] Build the native web server executable with
      `python SemanticScript/tools/sem.py build experiments/realtime-auction-arena/server`.
- [x] Start the built executable on `127.0.0.1:18083` from the E2E harness.
- [x] Serve `GET /healthz` with status `200`, `apiVersion: v1`, `ok: true`,
      and echoed `X-Request-Id`.
- [x] Serve `GET /readyz` with status `200`, `apiVersion: v1`, `ok: true`,
      and echoed `X-Request-Id`.
- [x] Serve `GET /metrics` with Prometheus-style bootstrap metrics text.
- [x] Expose runtime-backed request, auth, command, bid, rate-limit, and
      auction-count metrics, plus active SSE replay gauges/counters while
      live streaming fanout remains open.
- [x] Serve `GET /api/v1` with versioned route metadata.
- [x] Serve authenticated `GET /api/v1/auctions` from persisted SQLite rows.
- [x] Serve unknown API routes as status `404` with stable error code
      `not_found`.
- [x] Attach `X-Api-Version`, `X-Request-Id`, `X-Max-Body-Bytes`, and
      `X-Route-Path` headers on verified API responses.
- [x] Serve `GET /api/v1/session` as status `401` with stable error code
      `unauthorized` before login and after logout.
- [x] Serve `GET /api/v1/session` as status `200` with seeded auctioneer
      principal data when the active bearer token is supplied.
- [x] Serve `POST /api/v1/auctions` as status `201` after bearer auth,
      JSON validation, idempotency lookup, SQLite insert, event append, and
      idempotency-cache write.
- [x] Serve `GET /api/v1/auctions/:auctionId` as an authenticated persisted
      auction snapshot.
- [x] Serve `POST /api/v1/auctions/:auctionId/start` as an authenticated,
      idempotent SQLite transaction that moves a draft auction to running.
- [x] Serve `POST /api/v1/auctions/:auctionId/bids` as an authenticated,
      idempotent SQLite transaction that accepts a valid bid and advances the
      auction revision.
- [x] Reject auctioneer-token bid attempts and require the seeded bidder role
      plus bidder write scope for the registered bid route.
- [x] Serve `GET /api/v1/auctions/:auctionId/events` as authenticated JSON
      replay of persisted auction events.
- [x] Authorize the executable event replay route for the seeded auctioneer and
      bidder viewer principals before reading replay rows.
- [x] Persist accepted-command audit rows for create/start/bid and verify them
      from the E2E harness.
- [x] Serve command writes missing `Idempotency-Key` as status `400` with
      stable error code `missing_idempotency_key`.
- [x] Serve `POST /api/v1/auth/login` as status `401` with stable error code
      `invalid_credentials` for bad credentials.
- [x] Serve JSON write routes with non-JSON `Content-Type` as status `415`
      with stable error code `unsupported_media_type`.
- [x] Serve `POST /api/v1/auth/login` as status `200` for the seeded
      `auctioneer` account after bcrypt verification.
- [x] Serve `POST /api/v1/auth/login` as status `200` for the seeded `bidder`
      account and return bidder session data when its active bearer token is
      supplied.
- [x] Serve `POST /api/v1/auth/refresh` as status `200` for the current
      refresh token, rotate both tokens, and reject refresh replay.
- [x] Serve `POST /api/v1/auth/logout` as status `200` for the current refresh
      token and revoke the process-local demo session.
- [x] Return cached command responses for repeated create/start/bid
      idempotency keys with the same request body.
- [x] Return status `409` with stable error code `idempotency_conflict` when a
      create/start/bid idempotency key is reused with a different body.
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
- [x] Split high-noise runtime constants, SQL statement text, and static wire
      envelopes out of `server/src/main.sem` into focused imported modules.
- [x] Split shared HTTP helpers and repeated static envelope writers out of
      `server/src/main.sem` into `server/src/http_helpers.sem`.
- [x] Split executable server behavior into large context modules:
      `server_context`, `auth_context`, `observability_context`,
      `auction_context`, `event_context`, and `chat_context`, leaving
      `main.sem` focused on route ABI wiring.
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
- [x] Define auth hardening contracts for JWT secret config shape, runtime time
      claim validation, login rate-limit buckets, durable auth audit events,
      and JWT denylist lookup/cleanup.
- [x] Add parse-oriented auth hardening test markers for JWT config/time
      claims, denylist behavior, login rate limits, auth audit events, and
      negative authz cases.

## P0 - Source Health Gate

- [ ] Make `python SemanticScript/tools/sem.py check --json
      experiments/realtime-auction-arena/server` pass with `sourceOk: true`,
      zero compile-blocking strict/lint diagnostics, and no unresolved
      cross-context symbol references.
- [ ] Add a CI/preflight gate that fails when the server build is green but
      the source-health lane is red.

## P0 - Make Auth Actually Work

- [x] Add a real bcrypt adapter or stdlib binding used by the server runtime.
- [x] Enforce bcrypt's 72-byte password input limit in the live login path.
- [x] Add base64url encode support for token material.
- [x] Add HMAC-SHA256 JWT signing/verification support.
- [x] Keep auction-specific JWT claims in `server/src/auth_context.sem`; `standard.jwt`
      exposes generic payload signing and signature verification only.
- [x] Add secure random bytes for JWT `jti` values and refresh tokens.
- [x] Load JWT signing secrets from environment or config when
      `AUCTION_ARENA_JWT_SECRET` is present and at least 32 bytes; deterministic
      local demo fallback remains for development.
- [x] Create a deterministic local seeded auctioneer flow for development.
- [x] Implement `POST /api/v1/auth/login`.
- [x] Parse and validate login JSON for the seeded executable path.
- [x] Verify bcrypt password hashes.
- [x] Rate-limit login attempts with executable SQLite `rate_limit_buckets`
      rows at 10 attempts per submitted username per 60000 ms window.
- [x] Issue access JWTs with issuer, audience, subject, role, scopes,
      expiration, issued-at, not-before, and token id claims.
- [x] Replace the fixed demo expiration with `now + 900s` and validate `exp`,
      `iat`, and `nbf` against runtime time.
- [x] Issue opaque refresh tokens and store only hashed refresh-token material
      in process-local demo state.
- [ ] Replace process-local active-session state with durable multi-session
      lookup through `sessions`/`refresh_tokens`, so session, refresh, logout,
      and JWT denylist checks survive process restart.
- [ ] Add live restart-safety coverage: login, restart server, verify session,
      refresh, logout, stale-token rejection, refresh replay rejection, and
      disabled-user rejection still work from durable auth state.
- [x] Append durable login success/failure audit events for accepted,
      invalid-credential, and rate-limited login decisions.
- [x] Implement `POST /api/v1/auth/refresh` for the process-local demo token.
- [x] Verify refresh token hash and session state.
- [x] Rotate refresh tokens on every use.
- [x] Revoke old refresh tokens.
- [x] Implement `POST /api/v1/auth/logout` for the process-local demo token.
- [x] Revoke process-local demo session state.
- [x] Define the JWT denylist plan for active JWT ids until expiration in
      `server/src/auth.sem`, backed by the existing `revoked_jwts` schema
      contract.
- [x] Wire executable JWT denylist lookup and cleanup into logout/session with
      `standard.jwt` claim extraction for active access-token `jti` values.
- [x] Implement authenticated `GET /api/v1/session` for the active bearer
      token.
- [x] Protect registered auctioneer command routes by seeded role and scope.
- [x] Protect the registered bid route by seeded bidder role and scope.
- [x] Protect future admin, service, viewer-scope, and full decoded-scope
      policies once those handlers/principals exist.
- [x] Make missing or short `AUCTION_ARENA_JWT_SECRET` fatal in production
      startup mode while preserving the deterministic local demo fallback for
      development.
- [x] Add live production-config coverage that proves production mode fails
      readiness/startup without a valid JWT secret and succeeds with a valid
      secret.
- [ ] Replace seeded process-local role checks with durable principal lookup
      plus decoded-scope authorization for every protected route.
- [x] Add live API tests for bad JWT signature, stale access token, and refresh
      replay.
- [x] Add live API tests for disabled user, expired token, wrong audience, and
      insufficient role.
- [x] Add live API tests for wrong-role bid denial on the registered bid
      route.
- [x] Add live API tests for bad password, successful login, bearer session,
      refresh, logout, and post-logout unauthorized session.

## P0 - Make Persistence Actually Work

- [x] Add a SQLite runtime adapter or FFI layer usable by the web server target.
- [x] Add explicit schema initialization from `server/sql/schema.sql`.
- [x] Make `/readyz` fail when database open/schema initialization fails.
- [x] Use SQLite transactions for create/start/bid command handlers.
- [x] Factor repeated `BEGIN IMMEDIATE` / deferred rollback / `COMMIT` rows
      into the executable `persistence_tx` transaction helper module with
      rollback defers.
- [x] Ensure registered auction command writes commit auction state, emitted
      events, audit, request log, and idempotency state atomically.
- [x] Ensure create/start/bid/extend/close accepted command writes commit
      auction state, domain events, accepted audit rows, request logs, and
      idempotency state atomically.
- [x] Keep executable event exposure after commit; live fanout broadcast remains
      part of the long-lived live SSE work.
- [x] Roll back create/start/bid state changes on command failure with deferred
      rollback guards.
- [x] Return stable errors for every rejected lifecycle/bid reason used by the
      executable start/extend/close/bid handlers.
- [x] Persist rejected bids with reason, actor, amount, auction revision, and
      request id.
- [ ] Replace raw request-body idempotency hash surrogates with canonical JSON
      request hashing for all idempotent command routes.
- [ ] Make idempotency replay lookup, command mutation, response capture, and
      idempotency row write fully atomic for concurrent duplicate requests.
- [x] Persist request logs for registered auction command accepts and bid
      rejects with request id, route, status, actor, duration, and stable error
      code.
- [x] Add persistence tests for migration idempotency, event sequence
      uniqueness, rejected bid storage, and rollback. Validate with
      `python experiments/realtime-auction-arena/server/tests/persistence_sqlite_tests.py`.
- [x] Add live persistence coverage for create/start/bid idempotency replay,
      persisted event replay, scoped idempotency rows, accepted/rejected audit
      rows, rejected bid rows, and command request logs.

## P0 - Make Auction APIs Actually Work

- [x] Wire route-param extraction into auction snapshot/start/bid/event
      handlers for `:auctionId`.
- [x] Add query parsing for event replay pagination and SSE replay cursors.
- [x] Add typed JSON body parsing with strict unknown-field handling for
      registered auction command bodies.
- [x] Add content-type validation for registered JSON write routes.
- [x] Generate a request id when `X-Request-Id` is absent and reflect it in
      headers and dynamic JSON-built envelope bodies. Static pre-rendered
      envelopes still carry the compiled fallback id until they are moved to
      dynamic formatting.
- [x] Add method-not-allowed responses for unsupported methods on known paths.
      Validated by
      `python experiments/realtime-auction-arena/server/tests/e2e_api_smoke.py`.
- [x] Add clean body-size limit enforcement returning `413 payload_too_large`
      with common API headers and envelope body.
- [x] Implement `POST /api/v1/auctions`.
- [x] Implement `GET /api/v1/auctions/:auctionId`.
- [x] Implement `POST /api/v1/auctions/:auctionId/start`.
- [x] Implement `POST /api/v1/auctions/:auctionId/extend`.
- [x] Implement `POST /api/v1/auctions/:auctionId/close`.
- [x] Implement `POST /api/v1/auctions/:auctionId/bids`.
- [x] Require idempotency keys for currently registered command write routes.
- [x] Require idempotency keys for all registered auction/chat command routes.
- [x] Return cached command response for repeated create/start/bid idempotency
      keys.
- [x] Return stable rule-failure error codes for bid and lifecycle rejects.
- [x] Add API integration tests for successful auction lifecycle, unauthorized
      requests, forbidden role requests, idempotency replay, stale revision, and
      every bid reject reason.
- [x] Add API/E2E coverage for successful create/start/extend/close/bid/event
      replay, unauthorized requests, missing idempotency, idempotency replay,
      and idempotency conflict.
- [x] Add API/E2E coverage for strict unknown-field rejects, generated
      request-id headers, dynamic request-id envelope seeding, missing
      idempotency on every registered auction/chat command route, and stable
      `amount_too_high` bid rejects.

## P1 - Async Supervisor And Timers

- [x] Document the closest runtime-supported supervisor equivalent: current
      command routes serialize each accepted command through SQLite
      transactions, persist ordered auction event sequences, and expose the
      remaining route-to-supervisor integration gap in `/metrics`.
- [x] Receive create/start/bid/extend/close commands through bounded
      `standard.event` process queues.
- [x] Define bounded command queue, timer, shutdown, deterministic ordering,
      and command backpressure contracts in the supervisor contract artifact;
      executable queue operations now use libuv-backed async runtime bindings.
- [x] Receive timer expiration and shutdown command events through the
      executable bounded supervisor queue smoke.
- [x] Add executable deterministic queue ordering smoke for
      create/start/bid/extend/close/timer-expired/shutdown command events.
- [x] Add executable backpressure behavior for saturated command queues.
- [ ] Add fake-clock tests for anti-sniping and close timers.
- [x] Add `standard.event` strict process queues for bounded command-channel
      semantics and explicit `queue_full` backpressure.
- [ ] Add async `select`, cancelable timer producers, fake clock, and
      route-handler actor-loop integration to finish the production supervisor.
- [ ] Add fake-clock/select ordering tests for simultaneous bids versus timer
      expiry after those primitives are exposed.

## P1 - SSE Streaming And Replay

- [x] Implement authenticated JSON event replay at
      `GET /api/v1/auctions/:auctionId/events`.
- [x] Add opt-in `Accept: text/event-stream` SSE replay at
      `GET /api/v1/auctions/:auctionId/events`.
- [ ] Upgrade the executable SSE replay response to a true long-lived live
      fanout subscription.
- [x] Authenticate and authorize the executable event replay path
      before replay for seeded auctioneer and bidder principals.
- [x] Support `Last-Event-ID` and `?after=<eventId>` replay in JSON and SSE
      replay, with `Last-Event-ID` taking precedence.
- [x] Replay missed events from SQLite in committed sequence order for JSON and
      SSE replay, and define replay-before-live attachment ordering for the
      future long-lived SSE path.
- [x] Add stable `eventType` text beside numeric event codes in event replay
      rows for future SSE `event:` names.
- [x] Define heartbeat interval, disconnect cleanup, per-client queue capacity,
      and slow-client drop metric contracts for long-lived SSE.
- [x] Expose runtime-backed active SSE replay and slow-stream-drop metrics plus
      heartbeat/queue-capacity gauges while live fanout is still pending.
- [x] Pin the current executable limitation with tests/docs: `/events` now has
      authenticated JSON replay plus opt-in SSE replay frames, but true live
      fanout still waits on route-level fanout, cancellation, and queues.
- [x] Add standard-library-owned SSE stream APIs:
      `http.openSseStream`, `http.writeSseEvent`, `http.writeSseEventWithId`,
      `http.writeSseHeartbeat`, `http.closeSseStream`, and
      `http.clientDisconnected`, backed by runtimeBinding native hooks rather
      than compiler-specific `http.sse*` lowering.
- [x] Emit real heartbeat comments on executable SSE replay responses.
- [x] Check native disconnect state after each SSE frame write and decrement
      active stream metrics on every exit path.
- [ ] Remove live subscribers from the future fanout set when disconnects are
      observed.
- [ ] Add executable per-client bounded queues.
- [ ] Drop slow clients after queue overflow in the live fanout path and count
      the drop in runtime metrics.
- [x] Add focused API smoke coverage for event replay auth, cursor bounds,
      event type names, SSE metrics, and Last-Event-ID precedence.
- [x] Add focused API smoke coverage for opt-in SSE replay frames,
      Last-Event-ID precedence, and heartbeat output.
- [ ] Add multi-client broadcast, reconnect, periodic heartbeat, and slow-client
      tests once the route uses live fanout.

## P1 - Auction Floor Chat

- [x] Implement executable `POST /api/v1/auctions/:auctionId/chat/messages`
      with bidder auth, strict JSON `text` parsing, idempotency, SQLite
      `chat_messages` persistence, `chat.message.created` event append,
      replay ordering, text-only storage, and validation through
      `python experiments/realtime-auction-arena/server/scripts/full_demo.py --require-full`.
- [x] Implement executable
      `DELETE /api/v1/auctions/:auctionId/chat/messages/:messageId`
      with auctioneer moderation auth, idempotency, SQLite moderation
      persistence, accepted audit rows, and `chat.message.deleted` event append.
- [x] Implement executable
      `POST /api/v1/auctions/:auctionId/chat/messages/:messageId/report`
      with bidder auth, idempotency, SQLite moderation persistence, accepted
      audit rows including the report reason, and `chat.message.reported` event
      append.
- [x] Require bidder role for posting in executable chat policy helpers.
- [x] Require auctioneer/admin role for moderation in executable chat policy
      helpers.
- [x] Enforce chat-create rate limiting as 5 messages per 10000 ms actor
      window through executable SQLite bucket reads/writes.
- [x] Enforce max message byte length through executable chat policy helpers
      and the `chat_messages` schema check.
- [x] Sanitize/escape text before browser rendering by requiring JSON
      serializer output for response/replay payloads and text-only storage.
- [x] Contract-complete chat message and moderation persistence SQL.
- [x] Contract-complete `chat.message.created`, `chat.message.deleted`, and
      `chat.message.reported` auction-event inserts for replay.
- [x] Ensure chat does not change `AuctionState.revision` through executable
      revision-isolation helper and SQL that advances only event sequence.
- [x] Ensure chat participates in replay ordering through event sequence.
- [x] Keep real HTTP/2 or WebSocket chat as a later transport experiment after
      the SSE path is working.

## P1 - Observability And Security

- [x] Log request start and finish through middleware request counting and
      durable finish rows on auth/command paths.
- [x] Include request id, route pattern, status, actor id, duration, and error
      code in logs.
- [x] Redact JWTs, refresh tokens, passwords, and raw auth headers in live logs.
- [x] Audit accepted, rejected, denied, and failed command outcomes.
- [x] Hash or redact IP and user-agent fields before durable storage.
- [x] Expand `/metrics` to include active SSE clients, total bids, accepted
      bids, rejected bids by reason, chat accepted/rejected, auction counts by
      status, request counts by route/status, command latency, broadcast
      failures, login failures, and rate-limit hits.
- [x] Replace bootstrap/runtime-gap metric markers with runtime-backed counters
      and gauges as each persistence, SSE, auth, and command subsystem becomes
      executable.
- [x] Define allowed CORS origins in `server/docs/api-contract.md`.
- [x] Reject unsupported HTTP methods for registered API paths. Validated by
      `python experiments/realtime-auction-arena/server/tests/e2e_api_smoke.py`.
- [x] Reject unknown JSON fields where strict request models require it for
      registered auction and chat-create command bodies.
- [x] Add login, bid, and chat rate limiters.
- [x] Add CSRF plan before any cookie-authenticated writes in
      `server/docs/api-contract.md`.
- [x] Add metrics and audit tests for auth and command routes.
- [x] Protect `/metrics` with an operator/admin policy or explicit
      development-only mode so production metrics are not public.
- [x] Normalize completed request-log durations to non-zero persisted values
      and add live E2E assertions for command request-log duration rows.
- [ ] Add durable request-start rows, reusable request context, monotonic
      duration measurement source, and broader route-family request-log
      coverage.
- [ ] Remove or rename non-SSE runtime-gap metric markers once durable auth,
      reusable request-context logging, and idempotency gaps are closed.
- [x] Add runtime behavioral tests for metrics auth, production secret
      fail-fast, and request-log duration measurement.
- [ ] Add runtime behavioral tests for durable-session restart safety and
      canonical idempotency conflicts after those implementations land.

## P2 - Enterprise Hardening

- [x] Add OpenAPI-like route contract or generated endpoint index through
      `server/src/routes.sem`, `GET /api/v1`, and `server/docs/api-contract.md`.
- [x] Add stable error-code registry in `server/docs/api-contract.md`.
- [x] Add request/response examples for every route in
      `server/docs/api-contract.md`.
- [x] Add API version compatibility notes and future `/api/v2` deprecation
      plan in `server/docs/api-contract.md`.
- [x] Add event schema compatibility notes in `server/docs/api-contract.md`.
- [x] Add admin audit query filter contract in
      `server/docs/api-contract.md`, validated by
      `python experiments/realtime-auction-arena/server/tests/enterprise_contract_tests.py`.
- [x] Add pagination contracts for auctions, bids, and audit in
      `server/docs/api-contract.md`; event replay pagination is executable
      through `?after`/`Last-Event-ID` plus `?limit=1..200`.
- [x] Upgrade executable audit replay from timestamp-only `after` pagination to
      the full opaque cursor with an `audit_event_id` tiebreak.
- [x] Add server build-tape config settings in `server/build.sem`, validated
      by `python experiments/realtime-auction-arena/server/tests/enterprise_contract_tests.py`.
- [x] Add graceful shutdown plan in `server/docs/runtime-gaps.md` and
      `server/docs/api-contract.md`.
- [x] Add native HTTP fallback SIGINT/SIGTERM accept-loop shutdown: stop
      accepting, let the active handler finish, close the listen socket, and
      return `SS_HTTP_OK`.
- [x] Add SemanticScript-visible shutdown drain-state hook in `standard.http`
      and use it from server readiness/middleware so new command routes reject
      with `server_shutting_down` during drain.
- [ ] Add app-level shutdown finalization for non-SSE work: stop accepting,
      reject new commands, let accepted SQLite transactions finish, checkpoint
      and close SQLite, flush durable request/audit logs, and verify the grace
      deadline in a live harness.
- [ ] Expose SemanticScript-visible request cancellation tokens for non-SSE
      handlers so long-running auth, auction, chat, and audit work can abort
      during client disconnect or process drain.
- [x] Close and drain current executable SSE replay streams on every handler
      exit path, including heartbeat completion, disconnect detection, write
      failure, and active stream metric decrement.
- [ ] Add request cancellation tokens and close/drain future long-lived SSE
      fanout subscribers once async fanout exists.
- [x] Add database backup/export plan in `server/docs/api-contract.md`.
- [x] Add local development seed data for auctioneer and bidder principals,
      including password credential rows verified by the E2E harness.
- [x] Add load smoke for many bids and concurrent bidder clients through
      `python experiments/realtime-auction-arena/server/scripts/load_smoke.py`.
- [x] Add full server demo script: start server, initialize schema, seed admin,
      login, create auction, start auction, run scripted bidder clients, submit
      bids, send chat messages, close auction, and verify persisted audit,
      chat, and ordered event replay through
      `python experiments/realtime-auction-arena/server/scripts/full_demo.py --require-full`.
