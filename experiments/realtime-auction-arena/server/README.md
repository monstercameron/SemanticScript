# Auction Server

This subproject is the authoritative SemanticScript server for Realtime Auction
Arena. It owns auction state, validates bids, runs timing rules, authenticates
users, persists replayable events, and broadcasts live updates to browser
clients.

The server should feel like a compact enterprise backend, not a toy route
handler. Browser clients and the Win32 auctioneer console are only clients. The
server is the system of record.

## Current Executable Status

The checked-in server now proves the API shell, executable demo auth, and the
core SQLite-backed auction command path. The native webServer target builds and
the E2E harness verifies:

- `GET /healthz`, `GET /readyz`, `GET /metrics`, `GET /api/v1`, and
  authenticated `GET /api/v1/auctions`;
- stable `v1` envelopes, `X-Request-Id` echo, `X-Api-Version`,
  `X-Max-Body-Bytes`, `X-Route-Path`, and API 404 responses;
- SQLite database open/schema initialization during readiness;
- bcrypt-verified login for the seeded `auctioneer` and `bidder` demo
  accounts;
- HS256 bearer-token issuance from app-owned claim payloads, signature
  verification through `standard.jwt`, active-token session lookup,
  refresh-token rotation, logout revocation, bad-signature rejection,
  stale-token rejection after refresh, refresh replay rejection, and
  post-logout `401` behavior;
- bcrypt's 72-byte password boundary before verify;
- JSON write-route guardrails for unsupported media type and body size;
- command-route idempotency-key presence checks;
- persisted auction create/list/snapshot/start/bid/extend/close flows;
- seeded role/scope guards for registered auctioneer command routes and the
  bidder bid route;
- `405 method_not_allowed` envelopes for unsupported methods on known
  executable paths;
- idempotency replay and conflict handling for create/start/bid/extend/close
  commands;
- persisted auction event rows and bounded JSON event replay for
  create/start/bid/extend/close;
- durable accepted-command audit rows for create/start/bid/extend/close;
- executable chat create with bidder auth, strict JSON `text` parsing,
  text-only storage, `chat.message.created` event append, and replay ordering;
- runtime-backed request, auth, command, bid, rate-limit, and auction-count
  metrics plus explicit zero-valued SSE placeholder gauges/counters;
- oversized login bodies return a clean `413 payload_too_large` JSON envelope.

This is still not a production-complete backend. SQLite-backed
refresh-token/session persistence, full admin/service/viewer policy coverage,
a separate `403 forbidden` authz response, long-lived SSE streams, chat
delete/report persistence, refresh/logout/session audit rows, JWT denylist
checks, and production fatal-missing-secret mode are still open work tracked in
`TODO.md`. HS256 access-token signing, signature verification, environment JWT
secret override, process-local bcrypt-hashed refresh-token rotation, and the
persisted create/start/bid/extend/close/chat/event/audit happy path are
executable.

The executable API harness intentionally does not assert long-lived SSE
subscriptions, durable multi-session auth, chat delete/report moderation, or
admin audit-query behavior. Those remain target contracts until their runtime
storage and streaming integrations exist.

## Build Config And Hardening Knobs

`build.sem` is the current build-tape source of truth for local server defaults
and deployment config keys. The executable still uses static local defaults, but
the contract now names the settings production integration must supply:

```text
AUCTION_ARENA_HOST
AUCTION_ARENA_PORT
AUCTION_ARENA_DB
AUCTION_ARENA_JWT_SECRET
AUCTION_ARENA_MAX_JSON_BODY_BYTES
AUCTION_ARENA_CORS_ORIGINS
AUCTION_ARENA_RATE_LIMIT_MODE
AUCTION_ARENA_SSE_HEARTBEAT_MILLIS
AUCTION_ARENA_REQUEST_LOG_MODE
```

Production readiness must fail closed when required secret/config material is
missing or unsafe demo defaults are enabled. The source-embedded demo JWT secret
is still a development-only blocker tracked in `TODO.md`.

Graceful shutdown is documented as a server contract because the current native
webServer surface does not expose signal/cancellation hooks to SemanticScript.
The app-level order is: stop accepting requests, reject new commands, drain
accepted SQLite transactions, broadcast only committed events, close live
subscribers once SSE exists, checkpoint/close SQLite, and exit within the grace
deadline.

## Demo And Load Harnesses

The Python harnesses are intentionally external clients; they do not move
auction behavior into native/runtime code.

```powershell
python experiments/realtime-auction-arena/server/tests/enterprise_contract_tests.py
python experiments/realtime-auction-arena/server/scripts/load_smoke.py --bids 20 --concurrency 6
python experiments/realtime-auction-arena/server/scripts/full_demo.py --require-full
```

`load_smoke.py` builds and starts a clean local server by default, creates and
starts an auction, submits many accepted bids, then runs a small concurrent
stale-revision race and verifies the SQLite accepted-bid count.

`full_demo.py --require-full` validates the current executable demo path:
schema readiness, admin seed row, auctioneer login, auction create/start,
bidder login, accepted bids, chat create, auction close, ordered event replay,
chat persistence, and audit rows.

## Responsibilities

- Serve the browser client shell.
- Expose versioned JSON APIs for auctions, bids, chat, auth, metrics, and audit.
- Authenticate users with JWT access tokens and bcrypt password hashes.
- Enforce role and scope authorization on every command route.
- Own the auction rule engine.
- Emit Server-Sent Events for every state transition.
- Coordinate async bid commands, timer expiry, chat events, and auctioneer
  commands.
- Persist append-only auction events, chat events, audit events, request logs,
  idempotency keys, users, sessions, and refresh tokens.

## Planned Routes

```text
GET  /                         browser shell
GET  /healthz                  process liveness
GET  /readyz                   database/runtime readiness
GET  /metrics                  JSON or text operational metrics

POST /api/v1/auth/login
POST /api/v1/auth/refresh
POST /api/v1/auth/logout
GET  /api/v1/session

GET  /api/v1/auctions
POST /api/v1/auctions
GET  /api/v1/auctions/:auctionId
POST /api/v1/auctions/:auctionId/start
POST /api/v1/auctions/:auctionId/extend
POST /api/v1/auctions/:auctionId/close

POST /api/v1/auctions/:auctionId/bids
GET  /api/v1/auctions/:auctionId/events
GET  /api/v1/auctions/:auctionId/audit

POST /api/v1/auctions/:auctionId/chat/messages
DELETE /api/v1/auctions/:auctionId/chat/messages/:messageId
POST /api/v1/auctions/:auctionId/chat/messages/:messageId/report
```

Routes listed with create/list/snapshot/start/extend/close/bid/event replay are
executable as called out above. Audit query, chat, and true long-lived SSE
semantics remain planned enterprise routes.

## API Contract

Every JSON response should use the same envelope:

```json
{
  "apiVersion": "v1",
  "requestId": "req_123",
  "ok": true,
  "data": {},
  "error": null
}
```

Errors should be typed and stable:

```json
{
  "apiVersion": "v1",
  "requestId": "req_123",
  "ok": false,
  "data": null,
  "error": {
    "code": "unauthorized",
    "message": "Authentication is required",
    "details": {}
  }
}
```

Write routes should accept:

```text
X-Request-Id: req_...
Idempotency-Key: idem_...
Authorization: Bearer <access_jwt>
```

Browser cookie auth can be added later, but must include CSRF protection before
any cookie-authenticated write route is accepted.

## Model Shape Conventions

Use stable, prefixed ids everywhere. The prefix makes logs and debugging easier
and prevents accidentally passing one id kind into another API.

```text
auc_...      AuctionId
bid_...      BidId
evt_...      EventId
msg_...      ChatMessageId
user_...     UserId
sess_...     SessionId
rtok_...     RefreshTokenId
req_...      RequestId
idem_...     IdempotencyKey
audit_...    AuditEventId
```

Use integer money and time values. Do not use floats for bid amounts.

```text
MoneyAmountMinor       unsigned integer, currency minor unit or demo points
UtcMillis              wall-clock timestamp in milliseconds
MonotonicMillis        duration/deadline source for timers
DurationMillis         non-negative duration
AuctionRevision        incremented after every accepted state mutation
AuctionEventSequence   monotonically increasing per auction
```

API JSON can format timestamps as numbers first. Human-readable timestamps are
view concerns and can be derived later.

Until SemanticScript has first-class optionals everywhere, empty ids and zero
timestamps mean "absent" only when the surrounding status makes that legal. For
example, `currentWinner` is empty before the first accepted bid, and `closedAt`
is zero until the auction reaches a terminal state.

## Core Model Shapes

The shapes below are the target contract. They are intentionally explicit even
where SemanticScript may need language/runtime work before the exact source
spelling is pleasant.

### API Envelope

```text
record ApiError
  code ApiErrorCode
  message PublicErrorMessage
  details JsonText

record ApiMeta
  apiVersion ApiVersion
  requestId RequestId
  serverTime UtcMillis

record ApiEnvelope
  meta ApiMeta
  ok Bool
  data JsonText
  error ApiError
```

Rules:

- `ok=true` means `error` is empty and `data` contains a typed response payload.
- `ok=false` means `data` is empty and `error.code` is stable.
- `message` is safe for display; sensitive details stay in logs/audit only.
- `details` is machine-readable JSON for validation errors and rule failures.

### Auth And Principal

```text
enum UserRole
  viewer
  bidder
  auctioneer
  admin
  service

enum UserStatus
  active
  disabled
  locked

record UserAccount
  userId UserId
  email EmailAddress
  displayName DisplayName
  role UserRole
  status UserStatus
  createdAt UtcMillis
  disabledAt UtcMillis

record PasswordCredential
  userId UserId
  passwordHash BcryptPasswordHash
  passwordCost BcryptCost
  passwordUpdatedAt UtcMillis

record Principal
  userId UserId
  role UserRole
  sessionId SessionId
  scopes ScopeList
  authenticatedAt UtcMillis

record JwtAccessClaims
  issuer JwtIssuer
  audience JwtAudience
  subject UserId
  role UserRole
  scopes ScopeList
  issuedAt UtcMillis
  notBefore UtcMillis
  expiresAt UtcMillis
  jwtId JwtId

record RefreshTokenRecord
  refreshTokenId RefreshTokenId
  tokenHash RefreshTokenHash
  userId UserId
  sessionId SessionId
  createdAt UtcMillis
  expiresAt UtcMillis
  lastUsedAt UtcMillis
  revokedAt UtcMillis
  replacedByRefreshTokenId RefreshTokenId
```

Rules:

- JWT payloads carry authorization facts, not secrets.
- Refresh tokens are opaque random values; store only hashes.
- `disabledAt` invalidates future login and refresh attempts.
- Logout revokes refresh tokens and may add the current JWT `jti` to a denylist.
- Refresh rotation is durable only after `refresh_tokens` row updates run in one
  transaction: verify active row, revoke it, insert replacement, append audit.

### Auction Aggregate

```text
enum AuctionStatus
  draft
  scheduled
  running
  closing
  closed
  cancelled

record AuctionPolicy
  minimumIncrement MoneyAmountMinor
  antiSnipeWindow DurationMillis
  antiSnipeExtension DurationMillis
  maxBidAmount MoneyAmountMinor
  maxBidderNameBytes CByteCount
  maxChatMessageBytes CByteCount

record AuctionTiming
  startsAt UtcMillis
  closesAt UtcMillis
  startedAt UtcMillis
  closedAt UtcMillis
  durationMillis DurationMillis

record AuctionItem
  title AuctionItemTitle
  description AuctionItemDescription
  imageUrl Url

record AuctionState
  auctionId AuctionId
  revision AuctionRevision
  status AuctionStatus
  item AuctionItem
  policy AuctionPolicy
  timing AuctionTiming
  startingBid MoneyAmountMinor
  currentBid MoneyAmountMinor
  currentWinner UserId
  lastBidder UserId
  createdBy UserId
  createdAt UtcMillis
  updatedAt UtcMillis

record AuctionSnapshot
  auction AuctionState
  lastEventSequence AuctionEventSequence
  serverTime UtcMillis
  activeClientCount CUnsignedInt64
```

Rules:

- `revision` increments for every accepted mutation.
- `currentBid` is never lower than `startingBid`.
- `currentWinner` is empty until the first accepted bid.
- `lastBidder` prevents self-outbidding.
- `closed` and `cancelled` are terminal states.
- Anti-sniping only extends `closesAt`; it does not rewrite bid history.

### Bids

```text
enum BidStatus
  accepted
  rejected

enum BidRejectReason
  auction_not_found
  auction_not_running
  below_minimum_increment
  bidder_is_current_winner
  bidder_not_authorized
  amount_too_large
  duplicate_idempotency_key
  stale_expected_revision
  validation_error

record PlaceBidRequest
  bidderDisplayName DisplayName
  amount MoneyAmountMinor
  expectedRevision AuctionRevision

record BidRecord
  bidId BidId
  auctionId AuctionId
  bidderId UserId
  bidderDisplayName DisplayName
  amount MoneyAmountMinor
  status BidStatus
  rejectReason BidRejectReason
  requestId RequestId
  idempotencyKey IdempotencyKey
  createdAt UtcMillis

record BidDecision
  accepted Bool
  bid BidRecord
  newRevision AuctionRevision
  publicMessage PublicErrorMessage
```

Rules:

- A bid write is idempotent by `(auctionId, actorUserId, idempotencyKey)`.
- `expectedRevision` enables optimistic UI safety; stale revisions can warn or
  reject depending on policy.
- Rejected bids are still stored for audit and abuse/rate-limit tuning.
- Bid ordering uses server receive/commit order, not client timestamps.

### Commands

```text
record CommandContext
  commandId CommandId
  requestId RequestId
  idempotencyKey IdempotencyKey
  actor Principal
  receivedAt UtcMillis
  sourceIpHash IpHash
  userAgentHash UserAgentHash

record CreateAuctionCommand
  context CommandContext
  item AuctionItem
  policy AuctionPolicy
  timing AuctionTiming
  startingBid MoneyAmountMinor

record StartAuctionCommand
  context CommandContext
  auctionId AuctionId
  expectedRevision AuctionRevision

record PlaceBidCommand
  context CommandContext
  auctionId AuctionId
  request PlaceBidRequest

record ExtendAuctionCommand
  context CommandContext
  auctionId AuctionId
  extension DurationMillis
  reason AuctionExtensionReason

record CloseAuctionCommand
  context CommandContext
  auctionId AuctionId
  reason AuctionCloseReason
```

Rules:

- Route handlers produce commands; the supervisor owns mutation.
- Every command has a context, even if triggered internally.
- Commands are logged before execution and audited after decision.

### Events And SSE

Use a common event envelope plus typed payloads. This is easier to persist,
replay, and stream than ad hoc JSON per route.

```text
enum AuctionEventType
  auction.created
  auction.started
  bid.accepted
  bid.rejected
  auction.extended
  auction.closed
  chat.message.created
  chat.message.deleted
  chat.message.reported
  heartbeat

record AuctionEventEnvelope
  eventId EventId
  auctionId AuctionId
  sequence AuctionEventSequence
  schemaVersion EventSchemaVersion
  type AuctionEventType
  occurredAt UtcMillis
  actorId UserId
  requestId RequestId
  idempotencyKey IdempotencyKey
  payload JsonText

record BidAcceptedPayload
  bidId BidId
  bidderId UserId
  bidderDisplayName DisplayName
  amount MoneyAmountMinor
  newRevision AuctionRevision
  closesAt UtcMillis

record BidRejectedPayload
  bidId BidId
  bidderId UserId
  bidderDisplayName DisplayName
  amount MoneyAmountMinor
  reason BidRejectReason
  currentBid MoneyAmountMinor
  minimumAcceptedBid MoneyAmountMinor

record SseFrame
  eventId EventId
  eventType AuctionEventType
  retryMillis DurationMillis
  data AuctionEventEnvelope
```

Rules:

- `sequence` is unique and monotonic per auction.
- `schemaVersion` lets the SSE/event-log payload evolve independently from
  route versioning.
- SSE `id:` uses `eventId`; replay lookup can also use `sequence`.
- Payloads never contain password hashes, refresh tokens, JWTs, raw IPs, or
  private audit-only details.
- Heartbeats do not mutate auction revision.

### Chat

```text
enum ChatMessageStatus
  visible
  deleted
  reported
  hidden_by_moderator

record CreateChatMessageRequest
  text ChatMessageText
  clientNonce ClientNonce

record ChatMessage
  messageId ChatMessageId
  auctionId AuctionId
  authorId UserId
  authorDisplayName DisplayName
  status ChatMessageStatus
  text ChatMessageText
  createdAt UtcMillis
  deletedAt UtcMillis
  deletedBy UserId
  requestId RequestId
```

Rules:

- Store original text exactly as accepted, but escape on render.
- Apply byte-length limits before storing.
- Moderation creates new events instead of rewriting old event history.
- Chat never changes `AuctionState.revision`; it still uses the auction event
  sequence so SSE replay has one ordered stream per auction.

### Audit And Request Logs

```text
enum AuditResult
  accepted
  rejected
  denied
  failed

record AuditEvent
  auditEventId AuditEventId
  requestId RequestId
  actorId UserId
  actorRole UserRole
  action AuditAction
  resourceType ResourceType
  resourceId ResourceId
  result AuditResult
  reason AuditReason
  occurredAt UtcMillis
  ipHash IpHash
  userAgentHash UserAgentHash

record RequestLogEntry
  requestId RequestId
  method HttpMethod
  routePattern RoutePattern
  statusCode HttpStatusCode
  actorId UserId
  startedAt UtcMillis
  durationMillis DurationMillis
  responseBytes CByteCount
  errorCode ApiErrorCode
```

Rules:

- Audit is durable and queryable by admins.
- Request logs are operational and may be sampled later.
- Do not store raw IP/user-agent in the first pass; hash or redact them.

## Authentication

Use bcrypt for password storage and JWT for access tokens.

The current executable demo accounts are:

```text
username: auctioneer
password: auctioneer-demo-password
role: auctioneer

username: bidder
password: auctioneer-demo-password
role: bidder
```

`POST /api/v1/auth/login` parses JSON, verifies the password with the native
bcrypt adapter, builds the Realtime Auction Arena claim payload in
`server/src/auth_context.sem`, asks `standard.jwt` to sign that caller-owned payload,
returns an HS256 bearer JWT and an opaque random refresh token, stores only the
refresh token's bcrypt hash in process-local state, and activates a
process-local demo session. `GET /api/v1/session` verifies the
`Authorization: Bearer ...` token signature and accepts only the current active
access token. `POST /api/v1/auth/refresh` verifies the refresh hash and rotates
both tokens. `POST /api/v1/auth/logout` verifies the current refresh token and
revokes that process-local session.

Roles:

```text
viewer       read public auction state and chat
bidder       place bids and post chat
auctioneer   start, extend, and close auctions
admin        manage users and inspect audit logs
service      automation and test clients
```

JWT access token:

- short-lived, 5 to 15 minutes;
- signed by a server-side secret or key pair;
- includes `iss`, `aud`, `sub`, `role`, `scopes`, `iat`, `nbf`, `exp`, and
  `jti`;
- never stores password data, secrets, or sensitive profile fields.

Refresh token:

- opaque random token;
- stored hashed in SQLite;
- rotated on every refresh;
- revocable on logout;
- associated with user id, session id, creation time, expiry time, and last use.

Password storage:

- hash and verify through `standard.bcrypt`;
- enforce bcrypt's 72-byte input limit;
- perform the 72-byte plaintext check before `bcrypt.verify` or new hash
  generation, because bcrypt ignores bytes after that limit;
- store hash, cost, and `password_updated_at`;
- rate-limit login attempts;
- record failed login attempts in audit logs;
- support hash upgrade when the configured cost changes.

## Middleware Pipeline

Each request should flow through a consistent pipeline:

```text
requestId
structured request log start
body size limit
route match
auth parse
JWT verify
role/scope authorization
CSRF check for cookie-auth writes
idempotency lookup for write commands
handler
audit append for command routes
response envelope
structured request log finish
```

This pipeline is also a language stress test. It should push SemanticScript
toward reusable middleware contracts, typed route params, structured errors,
and shared request context.

## Command Model

Route handlers should not mutate auction state directly. They should parse,
authenticate, authorize, validate the command shape, and send a command to the
auction supervisor.

```text
HTTP route handler
  -> parse JSON
  -> authenticate principal
  -> authorize role/scope
  -> validate command shape
  -> send command to AuctionSupervisor
  -> await CommandResult
  -> return versioned envelope
```

Command types:

```text
CreateAuctionCommand
StartAuctionCommand
PlaceBidCommand
ExtendAuctionCommand
CloseAuctionCommand
CreateChatMessageCommand
DeleteChatMessageCommand
ReportChatMessageCommand
```

The supervisor should be the single writer for an auction. It should process
bid commands, timer expiry, manual close, and chat/moderation events in a
deterministic order.

## Auction Floor Chat

Chat is in scope as an enterprise live feature, but true HTTP/2 or WebSocket
transport is not required for the first pass.

MVP transport:

- clients post messages with
  `POST /api/v1/auctions/:auctionId/chat/messages`;
- the server broadcasts `chat.*` events over the auction SSE stream;
- reconnecting clients replay chat events through the same event-id mechanism
  as auction events.

Rules:

- `viewer` can read chat;
- `bidder` can post chat;
- `auctioneer` and `admin` can delete or moderate messages;
- all chat writes are authenticated;
- messages are rate-limited by user/session/IP where available;
- display text is escaped before rendering;
- chat events never affect bid ordering, timer state, or winner selection.

Representative events:

```json
{ "type": "chat.message.created", "auctionId": "A1", "messageId": "m1", "user": "Cam", "text": "Going once..." }
{ "type": "chat.message.deleted", "auctionId": "A1", "messageId": "m1", "reason": "moderated" }
{ "type": "chat.message.reported", "auctionId": "A1", "messageId": "m1", "reportId": "r1" }
```

## Logs, Audit, And Metrics

Keep three streams separate.

Application logs are operational and structured:

```json
{ "level": "info", "requestId": "req_123", "route": "/api/v1/auctions/A1/bids", "status": 200, "durationMs": 4 }
```

Audit logs are durable security/business history:

```json
{ "actorId": "user_7", "role": "auctioneer", "action": "auction.close", "auctionId": "A1", "result": "accepted" }
```

Auction events are replayable domain facts:

```json
{ "eventId": 184, "type": "bid.accepted", "auctionId": "A1", "amount": 220 }
```

Metrics should include:

- active SSE clients;
- total bids;
- accepted bids;
- rejected bids by reason;
- chat messages accepted/rejected;
- auction count by status;
- request count by route/status;
- command latency;
- event broadcast failures;
- login failures and rate-limit hits.

## Persistence Model

SQLite is enough for the demo, but the schema should model a real service:

```text
users
refresh_tokens
revoked_jwts
auctions
bids
auction_events
chat_messages
audit_events
request_log
idempotency_keys
rate_limit_buckets
```

Target row shapes:

```text
users
  user_id primary key
  email unique
  display_name
  role
  status
  created_at
  disabled_at
  locked_until

password_credentials
  user_id primary key references users(user_id)
  password_hash
  password_cost
  password_updated_at

refresh_tokens
  refresh_token_id primary key
  token_hash unique
  user_id references users(user_id)
  session_id
  created_at
  expires_at
  last_used_at
  revoked_at

revoked_jwts
  jwt_id primary key
  user_id
  expires_at
  revoked_at
  reason

auctions
  auction_id primary key
  revision
  status
  item_title
  item_description
  item_image_url
  starting_bid
  current_bid
  current_winner_user_id
  last_bidder_user_id
  minimum_increment
  anti_snipe_window_ms
  anti_snipe_extension_ms
  max_bid_amount
  max_bidder_name_bytes
  max_chat_message_bytes
  starts_at
  closes_at
  started_at
  closed_at
  created_by
  created_at
  updated_at

bids
  bid_id primary key
  auction_id references auctions(auction_id)
  bidder_user_id references users(user_id)
  bidder_display_name
  amount
  status
  reject_reason
  request_id
  idempotency_key
  created_at

auction_events
  event_id primary key
  auction_id references auctions(auction_id)
  sequence
  schema_version
  event_type
  occurred_at
  actor_user_id
  request_id
  idempotency_key
  payload_json

chat_messages
  message_id primary key
  auction_id references auctions(auction_id)
  author_user_id references users(user_id)
  author_display_name
  status
  text
  created_at
  deleted_at
  deleted_by_user_id
  request_id

audit_events
  audit_event_id primary key
  request_id
  actor_user_id
  actor_role
  action
  resource_type
  resource_id
  result
  reason
  occurred_at
  ip_hash
  user_agent_hash

request_log
  request_id primary key
  method
  route_pattern
  status_code
  actor_user_id
  started_at
  duration_ms
  response_bytes
  error_code

idempotency_keys
  idempotency_key
  actor_user_id
  auction_id
  route_pattern
  request_hash
  response_json
  status_code
  created_at
  expires_at

rate_limit_buckets
  bucket_key primary key
  subject_kind
  subject_id
  action
  window_start
  window_ms
  count
  blocked_until
```

Required uniqueness and indexes:

- `users.email` unique.
- `refresh_tokens.token_hash` unique.
- `auction_events(auction_id, sequence)` unique.
- `bids(auction_id, bidder_user_id, idempotency_key)` unique.
- `idempotency_keys(actor_user_id, auction_id, route_pattern, idempotency_key)`
  unique.
- Index `auction_events(auction_id, sequence)` for SSE replay.
- Index `bids(auction_id, created_at)` for bid history.
- Index `audit_events(actor_user_id, occurred_at)` for admin investigation.
- Index `request_log(started_at)` for operational diagnostics.

Idempotency should cache the first committed command response. If a request
fails before the command commits, the retry should be allowed to execute again.

Command transaction shape:

```text
begin
  check idempotency key
  load principal/session where needed
  load auction state
  validate command
  write state changes
  append auction/chat event
  append audit event
commit
broadcast event after commit
```

Broadcasting after commit keeps SSE clients from seeing events that were not
durably accepted.

## Internal Shape

```text
src/
  main.sem                     native route shell, timeout/middleware wiring, context imports
  server_context.sem           database bootstrap, health/readiness/metrics, shell handlers
  auth_context.sem             login, refresh, logout, session, bearer auth helpers
  observability_context.sem    metrics state, audit insert helpers, request-log helpers
  auction_context.sem          auction list/snapshot/create/start/extend/close/bid handlers
  event_context.sem            event type names and bounded JSON replay handler
  chat_context.sem             chat create handler plus registered delete/report guards
  runtime_constants.sem        HTTP/auth/JSON/bind/event constants imported by contexts
  sql_queries.sem              executable SQLite statement text imported by contexts
  wire_envelopes.sem           static native HTTP JSON wire bodies imported by helpers
  http_helpers.sem             common headers, envelope writers, content-type checks
  models.sem                   shared records, enums, and role types
  auction_domain.sem           records, enums, and validation rules
  auction_events.sem           event records and JSON encoding
  auction_supervisor.sem       async command loop once channels exist
  routes.sem                   route catalog and enterprise behavior contract
  auth.sem                     bcrypt login, JWT verification, role checks
  middleware.sem               request id, logging, auth, idempotency
  chat.sem                     chat commands and moderation rules
  persistence.sem              SQLite event/audit/log storage

tests/
  rule_tests.sem               deterministic rule checks
  auth_tests.sem               bcrypt/JWT/session contract checks
  chat_tests.sem               chat moderation and rate-limit checks
  api_tests.py                 external HTTP integration harness

docs/
  runtime-gaps.md              notes on missing language/runtime pieces
```

## Feature Pressure

This server should expose missing or immature features quickly:

- real long-lived SSE streams;
- async channels and `select`;
- cancelable monotonic timers;
- safe shared-state ownership;
- typed JWT claim validation, expiration checks, and key rotation;
- bcrypt password storage ergonomics;
- public-key signing primitives;
- cookie and CSRF helpers;
- rate limiter primitives;
- idempotency-key helpers;
- structured logging APIs;
- typed JSON body parsing;
- tagged event codecs;
- route/query parameter helpers;
- deterministic fake-clock tests;
- SQLite transaction/event-log ergonomics.

## First Milestone

The first working loop is now SQLite-backed JSON polling/replay, not an
in-memory placeholder:

1. Seed a local auctioneer user with a bcrypt password hash.
2. `POST /api/v1/auth/login`
3. `POST /api/v1/auctions`
4. `POST /api/v1/auctions/:id/start`
5. `POST /api/v1/auctions/:id/bids`
6. `GET /api/v1/auctions/:id`
7. `GET /api/v1/auctions/:id/events` returns committed event replay.
8. The E2E harness verifies accepted-command audit rows and scoped idempotency
   rows in SQLite.

Once that works, move bid handling behind an async supervisor and replace
polling with SSE broadcast, then add chat over POST plus the same SSE event
stream.
