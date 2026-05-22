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

The middleware reflects `X-Request-Id` as a response header when present. Static
response bodies still use `req_runtime_header_unavailable` until the runtime has
an ergonomic string builder for dynamic JSON response bodies.

Request ids:

- clients should send `X-Request-Id`
- accepted request ids are bounded to 128 bytes by contract
- the same request id is echoed in `X-Request-Id`
- JSON envelope bodies currently use `req_runtime_header_unavailable` until
  dynamic envelope formatting is wired across all handlers
- missing request ids fall back to `req_runtime_header_unavailable`

JSON write routes must require:

- `Content-Type: application/json`
- `Authorization: Bearer <access JWT>` when not anonymous
- `Idempotency-Key` for command routes except auth login
- body length no greater than `65536` bytes

Guard error envelopes are defined in `src/responses.sem`:

| Condition | HTTP status | Error code |
|---|---:|---|
| body exceeds `65536` bytes | 413 | `payload_too_large` |
| missing or non-JSON content type on JSON write route | 415 | `unsupported_media_type` |
| missing idempotency key on command route | 400 | `missing_idempotency_key` |
| reused idempotency key with different request body hash | 409 | `idempotency_conflict` |

Idempotency keys are currently persisted by `(scope, key, actor_user_id,
auction_id)` with an expiry filter. Create uses an empty `auction_id`; start and
bid use the route auction id. The executable path stores the raw request body as
the request-hash surrogate, so canonical JSON hashing is still planned. A replay
with the same scoped key and same body returns the original status and envelope.
A replay with a different body returns `idempotency_conflict`.

Observability contract:

- `GET /metrics` currently emits Prometheus-style bootstrap series.
- Planned request metrics use bounded route-pattern labels, not raw paths.
- Structured request logs use `http.request.start` and `http.request.finish`
  events with request id, route pattern, status, actor id, duration, and error
  code.
- Accepted create/start/bid command audit events are durable `audit_events`
  rows. Denied, rejected, auth, and request-finish audit/log rows remain planned.
- Audit and request logs must never store raw credentials, tokens, cookies, or
  password hashes.

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
| POST | `/api/v1/auctions/:auctionId/bids` | executable SQLite bid with idempotency and active bidder attribution |
| GET | `/api/v1/auctions/:auctionId/events` | executable JSON replay, not long-lived SSE |

Extend, close, audit query, chat, long-lived SSE, durable sessions,
admin/service/viewer-scope policy coverage, request logs, and rate limits remain
planned contracts. Registered auctioneer command routes and the bidder bid route
already enforce the seeded demo role/scope split.

## Route Contract Artifact

`server/src/routes.sem` is the OpenAPI-like source contract for the cataloged
server routes. It records method, path, handler name, auth policy, required
scopes, required path params, revision/idempotency requirements, rejection
codes, and current runtime status. `GET /api/v1` is the executable endpoint
index for routes that are actually registered today. The audit query route is a
README-level future route until it is added to the route catalog.

## Stable Error-Code Registry

| Code | HTTP status | Status |
|---|---:|---|
| `bad_request` | 400 | executable auth/body parse envelope |
| `invalid_credentials` | 401 | executable login envelope |
| `invalid_refresh_token` | 401 | executable refresh/logout envelope |
| `unauthorized` | 401 | executable auth guard envelope |
| `forbidden` | 403 | contract-only until authn/authz responses are split; registered wrong-role writes currently return `unauthorized` |
| `not_found` | 404 | executable explicit API not-found envelope |
| `auction_not_found` | 404 | executable auction lookup envelope |
| `payload_too_large` | 413 | executable body-limit envelope |
| `unsupported_media_type` | 415 | executable JSON write guard envelope |
| `idempotency_conflict` | 409 | executable command replay guard envelope |
| `stale_revision` | 409 | executable start/bid optimistic revision guard |
| `auction_not_running` | 409 | executable bid lifecycle guard |
| `bid_below_minimum` | 409 | executable bid amount guard |
| `missing_idempotency_key` | 400 | executable command guard envelope |
| `validation_failed` | 400 | executable generic command validation envelope |
| `database_unavailable` | 503 | executable SQLite failure envelope |
| `invalid_route_param` | 400 | contract-only until route-param validators split errors |
| `missing_expected_revision` | 400 | contract-only until revision parser splits errors |
| `lifecycle_rejected` | 409 | contract-only for extend/close lifecycle rules |
| `extension_out_of_bounds` | 400 | contract-only for extend command validation |
| `actor_not_bidder` | 403 | contract-only until bidder authorization executes |
| `amount_too_high` | 409 | contract-only until max-bid rejection has its own envelope |
| `same_bidder_in_a_row` | 409 | contract-only until self-outbid rejection executes |
| `replay_cursor_invalid` | 400 | contract-only until event cursor parsing executes |
| `chat_rejected` | 400 | contract-only for chat body/moderation rules |
| `message_not_found` | 404 | contract-only for chat moderation routes |
| `rate_limited` | 429 | contract-only until login/bid/chat limiters execute |

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
| `POST /api/v1/auctions/:auctionId/bids` | bearer, `Idempotency-Key`, `{"amount":120,"expectedRevision":1}` | `201`, accepted bid and advanced revision |
| `GET /api/v1/auctions/:auctionId/events` | bearer | `200`, JSON replay of committed auction events |
| `POST /api/v1/auctions/:auctionId/extend` | planned bearer command | planned `200` or stable lifecycle/validation error |
| `POST /api/v1/auctions/:auctionId/close` | planned bearer command | planned `200` or stable lifecycle/validation error |
| `GET /api/v1/auctions/:auctionId/audit` | planned admin bearer query | planned audit page response |
| `POST /api/v1/auctions/:auctionId/chat/messages` | planned bidder bearer command | planned chat event response |
| `DELETE /api/v1/auctions/:auctionId/chat/messages/:messageId` | planned moderator bearer command | planned moderation event response |
| `POST /api/v1/auctions/:auctionId/chat/messages/:messageId/report` | planned bidder bearer command | planned report event response |

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
