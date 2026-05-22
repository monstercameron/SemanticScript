# API Contract

All public JSON routes use API version `v1`. Versioned API routes live under
`/api/v1`, and responses include `X-Api-Version: v1`.

Successful JSON responses use:

```json
{
  "apiVersion": "v1",
  "requestId": "req_runtime_header_unavailable",
  "ok": true,
  "data": {},
  "error": null
}
```

Errors use:

```json
{
  "apiVersion": "v1",
  "requestId": "req_runtime_header_unavailable",
  "ok": false,
  "data": null,
  "error": {
    "code": "stable_code",
    "message": "Public message",
    "details": {}
  }
}
```

The middleware reflects `X-Request-Id` as a response header when present. When
the header is absent, the executable server generates a bounded opaque request
id and writes it to `X-Request-Id`. JSON-built dynamic response bodies seed the
same request id; static pre-rendered error bodies still use
`req_runtime_header_unavailable` until those envelopes move to dynamic
formatting.

Request ids:

- clients should send `X-Request-Id`
- accepted request ids are bounded to 128 bytes by contract
- the same request id is echoed in `X-Request-Id`; missing ids are generated
- dynamic JSON-built envelopes use the current request id
- static pre-rendered envelopes currently use `req_runtime_header_unavailable`
  until dynamic envelope formatting is wired across every handler

JSON write routes must require:

- `Content-Type: application/json`
- `Authorization: Bearer <access JWT>` when not anonymous
- `Idempotency-Key` for auction/chat command routes except auth login
- body length no greater than `65536` bytes
- strict request models reject unknown JSON object fields

Executable guard error envelopes are defined in `src/wire_envelopes.sem`:

| Condition | HTTP status | Error code |
|---|---:|---|
| body exceeds `65536` bytes | 413 | `payload_too_large` |
| missing or non-JSON content type on JSON write route | 415 | `unsupported_media_type` |
| missing idempotency key on command route | 400 | `missing_idempotency_key` |
| reused idempotency key with different request body hash | 409 | `idempotency_conflict` |

Idempotency keys are currently persisted by `(scope, key, actor_user_id,
auction_id)` with an expiry filter. Create uses an empty `auction_id`; start,
extend, close, and bid use the route auction id. The executable path stores the raw request body as
the request-hash surrogate, so canonical JSON hashing is still planned. A replay
with the same scoped key and same body returns the original status and envelope.
A replay with a different body returns `idempotency_conflict`.

Observability contract:

- `GET /metrics` emits Prometheus-style bootstrap info plus runtime-backed
  counters/gauges for routed requests, login outcomes, command outcomes, bid
  accepts, rate-limit hits, and active SSE clients.
- Metrics use bounded route-pattern and outcome labels, not raw paths, ids,
  usernames, tokens, IPs, user agents, or request bodies.
- Request finish logs persist `request_log` rows with route pattern, status,
  actor, duration, error code, idempotency key, and redacted client metadata.
- Accepted create/start/extend/close/bid command audit events are durable
  `audit_events` rows; login accepted/rejected and rejected bid outcomes are
  durable as public-safe audit rows.
- Audit and request logs must never store raw credentials, bearer tokens,
  refresh tokens, cookies, password hashes, raw IPs, or raw user agents.

Current executable route set:

| Method | Path | Status |
|---|---|---|
| GET | `/healthz` | executable |
| GET | `/readyz` | executable |
| GET | `/metrics` | executable |
| GET | `/api/v1` | executable |
| POST | `/api/v1/auth/login` | executable demo auth |
| POST | `/api/v1/auth/refresh` | executable demo auth |
| POST | `/api/v1/auth/logout` | executable demo auth |
| GET | `/api/v1/session` | executable demo auth |
| GET | `/api/v1/auctions` | executable SQLite list |
| POST | `/api/v1/auctions` | executable SQLite create with idempotency |
| GET | `/api/v1/auctions/:auctionId` | executable SQLite snapshot |
| POST | `/api/v1/auctions/:auctionId/start` | executable SQLite start with idempotency |
| POST | `/api/v1/auctions/:auctionId/extend` | executable SQLite extend with idempotency |
| POST | `/api/v1/auctions/:auctionId/close` | executable SQLite close with idempotency |
| POST | `/api/v1/auctions/:auctionId/bids` | executable SQLite bid with idempotency and active bidder attribution |
| GET | `/api/v1/auctions/:auctionId/events` | executable authenticated bounded JSON replay with `Last-Event-ID`/`?after`/`?limit` and stable `eventType`, not long-lived SSE |

Audit query, live chat handlers, long-lived SSE, durable sessions,
admin/service/viewer-scope policy coverage, all-route request start logging,
and non-auth rate-limit enforcement remain planned runtime work. Registered
auction command accepts and bid rejects persist durable request finish rows.
Chat route policy, message length,
sanitization, persistence SQL, event ordering, and revision-isolation contracts
are complete in `server/src/chat.sem` and `server/src/sql_queries.sem`.
Registered auctioneer command routes, the bidder bid route, and the event
replay route already enforce the seeded demo role/scope split. Event replay is
authorized for the active seeded auctioneer or bidder principals; production
viewer/admin/service authorization and the `403 forbidden` split remain
planned.

Auth hardening contract:

- `server/src/auth.sem` owns the JWT secret config shape, access-token
  time-claim validation rules, `revoked_jwts` denylist lookup/cleanup plan,
  durable auth audit event names, and login rate-limit bucket policy.
- The executable demo reads `AUCTION_ARENA_JWT_SECRET` when present and at
  least 32 bytes, otherwise falls back to the deterministic local demo secret;
  issues `iat`/`nbf` from runtime UTC seconds with `exp = iat + 900`; validates
  stored active-token time bounds on session; enforces login buckets in
  SQLite; and writes durable login accepted/rejected audit rows. Process-local
  sessions, durable refresh-token/session rows, refresh/logout/session audit
  rows, typed JWT claim extraction for arbitrary incoming tokens, and
  `revoked_jwts` denylist lookup remain planned.

Unsupported methods on known executable paths are registered to return
`405 method_not_allowed`. The method guard is registered explicitly for health,
readiness, metrics, API index, auth, session, auction list/create, auction
snapshot, start, extend, close, bid, and event-replay paths. Unknown paths
remain native dispatcher/not-found behavior.

## Route Contract Artifact

`server/src/routes.sem` is the OpenAPI-like source contract for the cataloged
server routes. It records method, path, handler name, auth policy, required
scopes, required path params, revision/idempotency requirements, rejection
codes, and current runtime status. `GET /api/v1` is the executable endpoint
index for routes that are actually registered today. The audit query route is a
README-level future route until it is added to the route catalog.

## Auction Floor Chat Contract

The chat create route is executable. Chat delete/report routes are registered
guards in `server/src/chat_context.sem` while full moderation persistence
remains contract work. Their source of truth is `server/src/chat.sem`, with SQL
text in `server/src/sql_queries.sem`:

- `POST /api/v1/auctions/:auctionId/chat/messages` requires bidder
  `chat:write`, `Idempotency-Key`, JSON text that is non-empty and at most
  `1000` bytes, and the per-actor/per-auction chat rate-limit window.
- `DELETE /api/v1/auctions/:auctionId/chat/messages/:messageId` requires
  auctioneer or admin moderation authority with `chat:moderate`; repeated
  deletes are idempotent and do not emit duplicate delete events.
- `POST /api/v1/auctions/:auctionId/chat/messages/:messageId/report` requires
  bidder `chat:write`; repeated reports by the same actor are idempotent.
- Chat text is stored as text, never HTML. JSON responses and replay payloads
  must be emitted through the JSON serializer so control characters, quotes,
  backslashes, and browser-sensitive characters cannot break the envelope.
- Chat create/delete/report writes consume `auction_events.sequence`, replay
  through the same auction event stream as bids/lifecycle events, and must not
  change `AuctionState.revision`.

## Admin Audit Query Filter Contract

`GET /api/v1/auctions/:auctionId/audit` is a planned admin-only query. It is
not registered as an executable handler yet, but its filter contract is fixed:

| Query parameter | Default | Rule |
|---|---|---|
| `actorUserId` | omitted | exact `audit_events.actor_user_id` match |
| `actorRole` | omitted | one of `10`, `20`, `30`; rejects unknown role codes |
| `action` | omitted | exact action such as `auction.create`, `auction.start`, `bid.accepted` |
| `outcome` | omitted | one of `accepted`, `rejected`, `denied`, `failed` |
| `requestId` | omitted | exact request correlation id |
| `bidId` | omitted | exact bid id |
| `fromUtcMillis` | omitted | inclusive lower bound on `created_at` |
| `toUtcMillis` | omitted | exclusive upper bound on `created_at`; must be greater than `fromUtcMillis` when both are present |
| `limit` | `50` | integer `1..200` |
| `cursor` | omitted | opaque cursor returned by the previous page |

The response shape is `data.auditEvents[]` plus `data.page`. The page object
contains `limit`, `count`, `nextCursor`, and `hasMore`. Raw IP addresses,
user-agent strings, JWTs, refresh tokens, password hashes, and request bodies
must never appear in audit query responses.

## Pagination Contract

Paginated collection reads should use a common cursor shape unless a route
documents a compatibility exception:

- `limit` defaults to `50`, is capped at `200`, and rejects non-integer values.
- `cursor` is opaque to clients. Version `v1` cursors encode a stable ordered
  tuple, not a raw SQL offset.
- Results are ordered newest-first for admin/audit/history views and
  sequence-ascending for auction event replay.
- `data.page` contains `limit`, `count`, `nextCursor`, and `hasMore` for new
  collection pages. The executable event replay JSON fallback is the current
  exception and returns `after`, `limit`, `count`, and `nextAfter` directly in
  `data`.
- Cursor filters are bound to the same route and filter set that issued them;
  changing filters with an old cursor returns `validation_failed`.

Initial target ordering:

| Route family | Order key | Cursor tuple |
|---|---|---|
| `GET /api/v1/auctions` | `created_at DESC, auction_id DESC` | `createdAtUtcMillis,auctionId` |
| `GET /api/v1/auctions/:auctionId/events` | `sequence ASC` | `sequence` or `eventId` once SSE ids are exposed |
| `GET /api/v1/auctions/:auctionId/audit` | `created_at DESC, audit_event_id DESC` | `createdAtUtcMillis,auditEventId` |
| future bid history | `created_at DESC, bid_id DESC` | `createdAtUtcMillis,bidId` |

## Server Config And Shutdown Contract

`server/build.sem` declares the build-time defaults and deployment config keys.
Executable local defaults bind to `127.0.0.1:18083`, use
`auction_arena.sqlite3`, and keep the native webServer profile in development
mode. Production deployments should provide `AUCTION_ARENA_JWT_SECRET` as at
least 32 random bytes. The current executable uses that value for signing and
verification when present; the source literal remains only as deterministic
local-demo fallback until production startup-mode config can make missing
secrets fatal.

Graceful shutdown contract:

- stop accepting new HTTP requests;
- reject new supervisor commands with `server_shutting_down`;
- drain accepted command transactions through commit/rollback;
- broadcast only committed events;
- close SSE subscribers after a final heartbeat/error frame when SSE exists;
- checkpoint or safely close SQLite handles;
- exit after the configured grace period, then rely on the process manager for
  hard termination.

The current executable does not have a signal/cancellation API exposed to
SemanticScript. The Python E2E, load, and demo scripts terminate the local
process after requests complete and validate that this does not leave the demo
database unreadable.

## Stable Error-Code Registry

| Code | HTTP status | Status |
|---|---:|---|
| `bad_request` | 400 | executable auth/body parse envelope |
| `invalid_credentials` | 401 | executable login envelope |
| `invalid_refresh_token` | 401 | executable refresh/logout envelope |
| `unauthorized` | 401 | executable auth guard envelope |
| `bad_signature` | 401 | contract-only until typed JWT failure envelopes split from `unauthorized` |
| `expired_token` | 401 | envelope constant exists; live session validates active-token stored `exp` but still returns `unauthorized` until failure envelopes split |
| `wrong_audience` | 401 | contract-only until typed JWT audience validation executes |
| `token_revoked` | 401 | contract-only until `revoked_jwts` lookup executes |
| `forbidden` | 403 | contract-only until authn/authz responses are split; registered wrong-role writes currently return `unauthorized` |
| `insufficient_role` | 403 | contract-only until the 403 authz split executes |
| `not_found` | 404 | executable explicit API not-found envelope |
| `method_not_allowed` | 405 | registered wrong-method envelope for known paths |
| `auction_not_found` | 404 | executable auction lookup envelope |
| `payload_too_large` | 413 | executable body-limit envelope |
| `unsupported_media_type` | 415 | executable JSON write guard envelope |
| `idempotency_conflict` | 409 | executable command replay guard envelope |
| `stale_revision` | 409 | executable start/extend/close/bid optimistic revision guard |
| `auction_not_running` | 409 | executable bid lifecycle guard |
| `bid_below_minimum` | 409 | executable bid amount guard |
| `missing_idempotency_key` | 400 | executable command guard envelope |
| `validation_failed` | 400 | executable generic command validation envelope |
| `database_unavailable` | 503 | executable SQLite failure envelope |
| `invalid_route_param` | 400 | contract-only until route-param validators split errors |
| `missing_expected_revision` | 400 | contract-only until revision parser splits errors |
| `lifecycle_rejected` | 409 | executable extend/close lifecycle guard |
| `extension_out_of_bounds` | 400 | executable extend command validation |
| `actor_not_bidder` | 403 | contract-only until bidder authorization executes |
| `amount_too_high` | 409 | executable max-bid rejection envelope |
| `same_bidder_in_a_row` | 409 | contract-only until self-outbid rejection executes |
| `replay_cursor_invalid` | 400 | contract-only stable code; executable out-of-range cursor/limit failures currently use `validation_failed` and decimal parsing is prefix-permissive |
| `chat_rejected` | 400 | contract-complete for chat body/moderation rules |
| `message_not_found` | 404 | contract-complete for chat moderation routes |
| `rate_limited` | 429 | executable for chat create; contract-complete for future moderation rate limits |

## Route Examples

Examples show the contract shape. Rows marked planned are not registered
handlers yet.

| Route | Request | Response |
|---|---|---|
| `GET /healthz` | `X-Request-Id: req_...` | `200`, `ok:true`, `data.status:"ok"` |
| `GET /readyz` | `X-Request-Id: req_...` | `200`, `ok:true`, `data.ready:true` |
| `GET /metrics` | `X-Request-Id: req_...` | `200` Prometheus text with bootstrap and runtime-gap series |
| `GET /api/v1` | `X-Request-Id: req_...` | `200`, executable route strings |
| `POST /api/v1/auth/login` | `{"username":"auctioneer","password":"auctioneer-demo-password"}` | `200`, bearer access token, refresh token, user |
| `POST /api/v1/auth/refresh` | `{"refreshToken":"..."}` | `200`, rotated bearer and refresh tokens |
| `POST /api/v1/auth/logout` | `{"refreshToken":"..."}` | `200`, `data.loggedOut:true` |
| `GET /api/v1/session` | `Authorization: Bearer <access_jwt>` | `200`, authenticated seeded principal |
| `GET /api/v1/auctions` | `Authorization: Bearer <access_jwt>` | `200`, persisted auction list |
| `POST /api/v1/auctions` | bearer, `Idempotency-Key`, auction JSON | `201`, persisted draft auction |
| `GET /api/v1/auctions/:auctionId` | bearer | `200`, persisted auction snapshot |
| `POST /api/v1/auctions/:auctionId/start` | bearer, `Idempotency-Key`, `{"expectedRevision":0}` | `200`, running auction revision |
| `POST /api/v1/auctions/:auctionId/extend` | bearer, `Idempotency-Key`, `{"expectedRevision":1,"extendByMillis":60000}` | `200`, running auction with advanced close time and revision |
| `POST /api/v1/auctions/:auctionId/close` | bearer, `Idempotency-Key`, `{"expectedRevision":4}` | `200`, closed auction with final bid/winner fields |
| `POST /api/v1/auctions/:auctionId/bids` | bearer, `Idempotency-Key`, `{"amount":120,"expectedRevision":1}` | `201`, accepted bid and advanced revision |
| `GET /api/v1/auctions/:auctionId/events` | bearer, optional `Last-Event-ID`, `?after`, `?limit=1..200` | `200`, bounded JSON replay of committed auction events |
| `GET /api/v1/auctions/:auctionId/audit` | planned admin bearer query | planned audit page response |
| `POST /api/v1/auctions/:auctionId/chat/messages` | contract-complete bidder bearer command | `chat.message.created` event response when handler is registered |
| `DELETE /api/v1/auctions/:auctionId/chat/messages/:messageId` | contract-complete moderator bearer command | `chat.message.deleted` event response when handler is registered |
| `POST /api/v1/auctions/:auctionId/chat/messages/:messageId/report` | contract-complete bidder bearer command | `chat.message.reported` event response when handler is registered |

## Version Compatibility

`v1` response envelopes keep `apiVersion`, `requestId`, `ok`, `data`, and
`error` stable. Additive fields may appear inside `data` or `error.details`.
Changing envelope shape, renaming stable error codes, changing route semantics,
or removing fields requires a future `/api/v2`. A future `/api/v2` must keep
`/api/v1` available during the demo branch and document any deprecation in the
server README before removing a v1 route.

## Event Schema Compatibility

Auction events use a route API version and a separate event `schemaVersion`.
For schema version `1`, consumers should treat new event object fields as
additive, ignore unknown fields, and key replay by auction id plus sequence.
Changing event type meanings, sequence semantics, or required payload fields
requires a new event schema version even if the HTTP route remains `/api/v1`.

## Event Replay Contract

`GET /api/v1/auctions/:auctionId/events` currently returns JSON, not a
long-lived `text/event-stream`. The executable replay reads committed
`auction_events` rows where `sequence > cursor`, ordered by sequence ascending.
The cursor comes from `Last-Event-ID` when present, otherwise from `?after`;
`Last-Event-ID` wins when both are supplied. `?limit` is optional and must be in
the inclusive range `1..200`; the default is `200`. The current executable uses
the standard decimal-prefix parser, so strict junk-after-number rejection is
still planned.

Each event row includes `sequence`, `auctionRevision`, stable `eventType`,
numeric `eventTypeCode`, `payload`, and `createdAtUtcMillis`. The response
`data` includes `auctionId`, `after`, `limit`, `events`, `count`, and
`nextAfter`. `nextAfter` is the last returned sequence, or the input cursor when
no rows are returned.

Long-lived SSE target behavior:

- authenticate and authorize the subscriber before replay;
- replay committed SQLite events before attaching to live fanout;
- send heartbeat comments every `15000` ms without consuming event sequence;
- remove disconnected clients from the per-auction fanout set;
- use a per-client outbound queue capped at `256` events;
- close only the slow subscriber on queue overflow and increment
  `auction_server_sse_slow_client_drops_total`;
- keep broadcast after commit so clients never observe rolled-back events.

The executable `/metrics` endpoint publishes runtime-backed request/auth/bid
and rate-limit series, zero-valued SSE gauges/counters, and the configured
heartbeat/queue capacity. Long-lived SSE fanout, heartbeat writes, disconnect
detection, and slow-client handling remain blocked on native streaming response
and cancellation APIs.

## CORS And CSRF Contract

The current executable does not emit CORS headers. The allowed-origin policy is:
no wildcard origins; local development may allow explicit `http://127.0.0.1:*`
and `http://localhost:*` browser origins; production must use an explicit
deployment allowlist. Browser cookie authentication is not enabled. Before any
cookie-authenticated write route is accepted, the server must require SameSite
cookies, verify `Origin` or `Referer`, require an unguessable CSRF token bound
to the session, and reject missing or mismatched CSRF material before command
execution.

## SQLite Backup And Export Plan

The local SQLite database is `server/auction_arena.sqlite3` with WAL sidecar
files. Backups should use SQLite's online backup API or `.backup` from a read
connection while the server is running; cold file copies must include the
`-wal` and `-shm` files or checkpoint WAL first. Logical exports should use
`.dump` or table-specific JSON export jobs for `auctions`, `bids`,
`auction_events`, `audit_events`, and `request_log`. Raw password hashes,
refresh-token hashes, JWT denylist rows, IP hashes, and user-agent hashes must
not be included in public demo exports.
