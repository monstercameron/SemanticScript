# Realtime Auction Arena

Realtime Auction Arena is a SemanticScript experiment for proving that the
language can drive a real, stateful, live application across three surfaces:

1. A SemanticScript native webserver that owns auction state and rules.
2. A browser client that renders live auction events over Server-Sent Events.
3. A Win32 auctioneer console that controls the auction through local HTTP APIs.

The point of this effort is not only to build a polished demo. It is also a
feature probe for missing language and runtime pieces: async tasks, SSE streams,
channels, timers, cancellation, shared state, JWT auth, bcrypt password
storage, JSON codecs, native HTTP client calls, structured logs, and Win32 GUI
integration.

The server-owned implementation checklist lives in
[server/TODO.md](server/TODO.md).

## Quickstart

Build and smoke-test the current server scaffold from the repo root:

```powershell
python SemanticScript/tools/sem.py build experiments/realtime-auction-arena/server
.\experiments\realtime-auction-arena\server\build\realtime_auction_arena_server.exe
```

In another shell:

```powershell
Invoke-WebRequest http://127.0.0.1:18083/healthz -UseBasicParsing
Invoke-WebRequest http://127.0.0.1:18083/metrics -UseBasicParsing
```

The executable currently serves the versioned API shell, static JSON envelopes,
bootstrap metrics, and auth/session runtime-gap responses. Full JWT login,
SQLite command transactions, dynamic auction routes, and SSE replay are still
tracked in [server/TODO.md](server/TODO.md).

## Demo Story

The intended 30-second demo:

1. Start the SemanticScript auction server.
2. Open the browser bidder client in two windows.
3. Open the Win32 auctioneer console.
4. Start an auction from the Win32 console.
5. Submit bids from both browser windows.
6. Watch accepted and rejected bid events stream to both clients.
7. Place a bid near the end of the countdown and see anti-sniping extend the
   auction.
8. Close the auction from the Win32 console or let the timer expire.
9. Show that the server announces the deterministic winner.

The browser should look like a live auction floor. The Win32 app should look
like an operator control room. The server should be the only authority for every
state transition.

## Folder Layout

```text
experiments/realtime-auction-arena/
  README.md
  server/
    SemanticScript native webserver and domain rule engine.
    src/
    tests/
    docs/
  browser-sse-client/
    Static HTML/CSS/JS browser bidder client rendered from SSE events.
    src/
    assets/
    tests/
  win32-auctioneer/
    Native Win32 SemanticScript operator console.
    src/
    resources/
    tests/
```

## Architecture

### Server

The server owns auction state and exposes HTTP/SSE endpoints.

Planned routes:

```text
GET  /                         static browser client shell
GET  /healthz                  process liveness
GET  /readyz                   database/runtime readiness
GET  /metrics                  operational counters

POST /api/v1/auth/login        issue access JWT and refresh token
POST /api/v1/auth/refresh      rotate refresh token and issue a new JWT
POST /api/v1/auth/logout       revoke current session/token
GET  /api/v1/session           current authenticated principal

GET  /api/v1/auctions          list auctions visible to the caller
POST /api/v1/auctions          create an auction
GET  /api/v1/auctions/:id      current auction snapshot
POST /api/v1/auctions/:id/start
POST /api/v1/auctions/:id/bids
POST /api/v1/auctions/:id/extend
POST /api/v1/auctions/:id/close
GET  /api/v1/auctions/:id/events
GET  /api/v1/auctions/:id/audit

POST /api/v1/auctions/:id/chat/messages
DELETE /api/v1/auctions/:id/chat/messages/:messageId
POST /api/v1/auctions/:id/chat/messages/:messageId/report
```

The server should eventually be organized around an async auction supervisor:

```text
AuctionSupervisor receives:
  StartAuction
  PlaceBid
  ExtendAuction
  CloseAuction
  ClientSubscribed
  ClientDisconnected
  TimerExpired

AuctionSupervisor emits:
  AuctionStarted
  BidAccepted
  BidRejected
  AuctionExtended
  AuctionClosed
  Heartbeat
```

The supervisor is a deliberate design pressure point. It should help decide
whether SemanticScript wants actor-style state ownership with channels, mutex
protected shared state, or both.

### Enterprise API Surface

The server should feel like a compact enterprise service from the start:

- all public API routes live under `/api/v1`;
- every response uses a structured envelope with `apiVersion`, `requestId`,
  `ok`, `data`, and `error`;
- every write accepts `X-Request-Id` and `Idempotency-Key`;
- every command writes an audit event;
- every handler emits structured application logs;
- every auth-sensitive route performs role and scope checks;
- SSE streams support reconnect and replay using `Last-Event-ID` or
  `?after=<eventId>`.

Example success envelope:

```json
{
  "apiVersion": "v1",
  "requestId": "req_123",
  "ok": true,
  "data": { "auctionId": "A1", "status": "running" },
  "error": null
}
```

Example error envelope:

```json
{
  "apiVersion": "v1",
  "requestId": "req_123",
  "ok": false,
  "data": null,
  "error": {
    "code": "bid_below_minimum",
    "message": "Bid must be at least 210",
    "details": { "currentBid": 200, "minimumIncrement": 10 }
  }
}
```

### Authentication And Authorization

Use JWT access tokens and bcrypt password storage.

Roles:

```text
viewer       can watch public auction state and chat
bidder       can place bids and post chat
auctioneer   can start, extend, and close auctions
admin        can manage users and inspect audit logs
service      can run automation and test APIs
```

Token model:

- short-lived access JWT, around 5 to 15 minutes;
- opaque refresh token stored hashed in SQLite and rotated on use;
- browser sessions can use HttpOnly SameSite cookies;
- Win32 and service clients can use `Authorization: Bearer <access_jwt>`;
- access-token denylist uses JWT `jti` only when logout/revocation requires it.

Representative JWT claims:

```json
{
  "iss": "semanticscript-auction-arena",
  "aud": "auction-api-v1",
  "sub": "user_123",
  "role": "auctioneer",
  "scope": ["auction:start", "auction:close"],
  "iat": 1710000000,
  "nbf": 1710000000,
  "exp": 1710000900,
  "jti": "tok_abc123"
}
```

Password rules:

- use `standard.bcrypt` for hashing and verification;
- enforce bcrypt's 72-byte password input limit;
- store only the bcrypt hash, cost, and update timestamp;
- rate-limit login attempts;
- add lockout or backoff after repeated failures;
- support hash-cost upgrade later.

### Auction Floor Chat

Add chat as a scoped live feature, not as a blocker for true HTTP/2 transport.

MVP chat uses HTTP/1.1-compatible routes:

- clients post messages with
  `POST /api/v1/auctions/:id/chat/messages`;
- the server broadcasts chat events over the existing auction SSE stream;
- moderators use delete/report routes;
- chat messages are persisted and replayable like auction events.

True HTTP/2, WebSocket, or bidirectional streaming can be a later runtime
transport experiment. The first pass should prove the domain and event model
with POST plus SSE.

Chat rules:

- `viewer` can read chat;
- `bidder` can post chat;
- `auctioneer` and `admin` can moderate;
- every message is rate-limited by user/session/IP where available;
- display text is escaped/sanitized before rendering;
- chat events never affect bid ordering or auction state.

### Browser SSE Client

The browser client should be intentionally thin:

- Connect to `GET /api/v1/auctions/:id/events`.
- Render current price, winner, countdown, and event feed.
- Submit bids through `POST /api/v1/auctions/:id/bids`.
- Submit chat messages through
  `POST /api/v1/auctions/:id/chat/messages`.
- Recover after reconnect by fetching `GET /api/v1/auctions/:id`.

The browser should not enforce auction rules. It can validate obvious form
mistakes, but every authoritative decision must come from the server.

### Win32 Auctioneer Console

The Win32 GUI is a separate native SemanticScript executable. It controls the
auction over local HTTP APIs and later may subscribe to the same event stream.

Initial controls:

- Item name input.
- Starting bid input.
- Minimum increment input.
- Countdown duration input.
- Start auction button.
- Extend 15 seconds button.
- Close auction button.
- Current status panel.
- Connected bidder count.
- Live audit/event list.
- Last rejected bids list.

This client stresses a different part of the platform: GUI event loops,
background HTTP calls, async-safe UI updates, and native packaging.

## Domain Rules

The first rule set should stay small but visible:

- A bid must be at least `currentBid + minimumIncrement`.
- A closed auction rejects every bid.
- A bidder cannot bid against themselves twice in a row.
- A bid inside the final anti-sniping window extends the auction.
- Manual close wins over later bids.
- Every accepted or rejected bid becomes an event.
- The winner is the highest accepted bid at close time.

## Event Shapes

Representative JSON events:

```json
{ "type": "auction.started", "auctionId": "A1", "item": "Vintage Synth", "startingBid": 100 }
{ "type": "bid.accepted", "auctionId": "A1", "bidder": "Cam", "amount": 180, "bidId": 12 }
{ "type": "bid.rejected", "auctionId": "A1", "bidder": "Alex", "amount": 150, "reason": "below_current_bid" }
{ "type": "auction.extended", "auctionId": "A1", "seconds": 15, "reason": "anti_sniping" }
{ "type": "auction.closed", "auctionId": "A1", "winner": "Cam", "amount": 220 }
{ "type": "chat.message.created", "auctionId": "A1", "messageId": "m1", "user": "Cam", "text": "Going once..." }
{ "type": "chat.message.deleted", "auctionId": "A1", "messageId": "m1", "reason": "moderated" }
```

These events should eventually become typed SemanticScript records with
`json.stringify.<TypeName>` codecs. A tagged-union event model would make this
demo better and should be tracked as a language feature if the current record
model is awkward.

## Model Boundaries

The detailed model contract lives in [server/README.md](server/README.md). The
core aggregates are:

- auth: `UserAccount`, `PasswordCredential`, `Principal`, `JwtAccessClaims`,
  and `RefreshTokenRecord`;
- auction: `AuctionState`, `AuctionPolicy`, `AuctionTiming`, `AuctionItem`,
  and `AuctionSnapshot`;
- bids: `PlaceBidRequest`, `BidRecord`, and `BidDecision`;
- commands: `CommandContext` plus create/start/bid/extend/close command
  records;
- events: `AuctionEventEnvelope` with typed payload records and `SseFrame`;
- chat: `ChatMessage` and moderation events;
- operations: `AuditEvent`, `RequestLogEntry`, idempotency keys, and rate-limit
  buckets.

Important invariants:

- bid amounts are integer minor units, never floats;
- ids use stable prefixes such as `auc_`, `bid_`, `evt_`, `user_`, and `req_`;
- `AuctionState.revision` increments after accepted state mutations;
- auction event sequences are monotonic per auction;
- event payloads carry a schema version separate from the route API version;
- chat does not mutate `AuctionState.revision`, but chat events still use the
  auction event stream for replay ordering;
- write commands are idempotent by actor, auction, and idempotency key;
- events broadcast only after the database transaction commits;
- JWTs, refresh tokens, password hashes, raw IPs, and private audit details
  never appear in SSE payloads.

## Missing Feature Pressure

This experiment should make gaps concrete.

| Area | Pressure |
| --- | --- |
| SSE | Need long-lived response streams, `sseOpen`, `sseWriteEvent`, heartbeat, close, and disconnect detection. |
| Async | Need real `start` / `await`, async `select`, task groups, and cancellation tokens. |
| Channels | Need bounded channels, backpressure behavior, `send`, `receive`, and closed-channel handling. |
| Timers | Need monotonic timers, cancel/reset timer, and fake-clock testing hooks. |
| HTTP | Need typed JSON body parsing, route/query params, static asset serving, and structured API errors. |
| JSON | Need tagged event encoding, enum codecs, optional fields, and good diagnostics for bad request bodies. |
| Auth | Need JWT sign/verify, bearer/cookie extraction, role/scope checks, refresh-token rotation, and revocation by `jti`. |
| Crypto | Need bcrypt ergonomics, base64url, HMAC/signature support, secure random bytes, and secret handling. |
| Logs | Need structured application logs, durable audit logs, request IDs, and command/event correlation ids. |
| Chat | Need multiplexed event streams, per-client queues, moderation events, and replayable message history. |
| State | Need a clear pattern for authoritative mutable state: actor ownership, mutexes, or both. |
| Persistence | Need SQLite transactions, event-log append, snapshot recovery, and replay since event id. |
| Win32 GUI | Need async-safe UI updates, native HTTP client calls, and possibly SSE consumption from a desktop app. |
| Testing | Need multi-client simulation, deterministic timers, disconnect/reconnect tests, and race checks. |

## Implementation Milestones

1. Versioned API shell with response envelopes, request IDs, and structured
   logs.
2. Seed admin user, bcrypt login, access JWT, refresh token, and role checks.
3. Server with in-memory auction state and JSON polling.
4. Browser client that polls versioned snapshot routes and posts bids.
5. Async auction supervisor with an internal command queue.
6. SSE broadcast from the server to multiple browser clients.
7. Timer-based automatic close and anti-sniping extension.
8. Auction-floor chat over POST plus the existing SSE stream.
9. Win32 auctioneer app that controls the server through authenticated HTTP.
10. SQLite event log, audit log, idempotency keys, and reconnect replay.
11. Deterministic test harness with fake time and simulated clients.

## Non-Goals For The First Pass

- Real payments.
- External SSO or OAuth provider integration.
- Multi-tenant security.
- Production-grade auction law/compliance behavior.
- Distributed server clustering.
- True HTTP/2 or WebSocket chat transport in the first pass.
- Browser framework complexity.

The first pass should stay focused on language/runtime pressure: live events,
async coordination, GUI control, and deterministic server-owned rules.
