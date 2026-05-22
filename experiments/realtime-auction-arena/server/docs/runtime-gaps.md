# Runtime Gaps

Worker 2 implemented the server scaffold up to the current SemanticScript native
HTTP/runtime surface.

## Executable Now

- Native `webServer` on `127.0.0.1:18083`.
- Registered routes for `/healthz`, `/readyz`, `/metrics`, `/api/v1`,
  `/api/v1/auth/*`, `/api/v1/session`, and `/api/v1/auctions`.
- Static JSON API envelopes with `apiVersion` and `requestId`.
- Response contracts are decomposed in `src/responses.sem` and validated with
  `jsonBody`.
- Response contracts now include guard envelopes for `payload_too_large`,
  `unsupported_media_type`, `missing_idempotency_key`, and
  `idempotency_conflict`.
- Middleware contracts now spell out request-id validation bounds, strict JSON
  content-type policy, idempotency scoping/replay rules, structured request log
  fields, audit redaction rules, metrics label rules, and `/api/v1` versioning.
- Middleware reads `X-Request-Id` and reflects it as a response header, falling
  back to `req_runtime_header_unavailable`.
- Body-size checks on registered JSON write routes using
  `http.requestBodyLength`.
- Content-type checks on registered JSON write routes.
- `POST /api/v1/auctions` requires `Idempotency-Key` before returning the
  fail-closed authorization envelope.
- Demo auth flow: JSON login body parsing, bcrypt verification for the seeded
  `auctioneer` account, bcrypt 72-byte input precheck, HS256 access-token
  signing with required arena claims, required-claim verification,
  process-local bcrypt-hashed refresh-token rotation, bearer session
  success/failure, logout, and post-logout revocation.
- Oversized login bodies are rejected by route code with `413
  payload_too_large` and the normal API headers/envelope.
- `standard.jwt` owns the HS256 runtimeBinding wrappers and declares the native
  JWT adapter source; the compiler no longer has JWT-specific call lowering.
- Prometheus-style bootstrap metrics.

## Blocked Or Stubbed

- Dynamic routes such as `/api/v1/auctions/:auctionId` are documented in
  `src/routes.sem`, but this app has not registered the auction/chat handlers
  or backed them with persistence yet.
- Production JWT hardening still needs environment/config secret loading,
  runtime-clock expiration checks, denylist persistence, and an asymmetric-key
  upgrade path. The current executable access token is HS256-signed and checked
  for required issuer/audience/subject/role/scope claim presence.
- The executable auth path uses native bcrypt for password verification and
  refresh-token hashing, but still needs SQLite user/session lookup, dummy
  verify timing equalization for unknown users, durable refresh-token rows, rate
  limiting, and audit writes.
- SQLite schema is available as `sqliteSchemaV1` in `src/persistence.sem`; a
  startup migration runner and readiness query are still future work.
- Long-lived SSE replay needs streaming response APIs, disconnect detection,
  bounded per-client queues, and heartbeats. Current native SSE support formats a
  one-shot event body only.
- Structured logs need a string builder or JSON writer plus time measurement.
  Middleware can stamp headers and declares `http.request.start` /
  `http.request.finish` fields now, but durable `request_log` rows are not
  wired.
- Request duration measurement requires a monotonic clock API that can be read at
  middleware start and route finish.
- Command-route idempotency still needs canonical request hashing plus SQLite
  `idempotency_keys` reads/writes in the same transaction as state changes.
- Audit writes need the SQLite transaction helper and route-level actor context;
  the contract names required fields and redaction rules, but no durable insert
  runs yet.
- Imported `JsonText` constants parse and compile, but native route execution
  returned 500 when handlers passed imported response bodies through the HTTP
  writer. `src/main.sem` keeps route-local `JsonText` bodies for now, while
  `src/responses.sem` records the decomposed contract. This should become a
  compiler/runtime test before the duplication is removed.

## Parent TODO Mapping

Safe to mark complete as scaffold/docs artifacts:

- Create `server/src/main.sem`.
- Add native webserver declaration and route table.
- Serve `GET /healthz`.
- Serve `GET /readyz`.
- Serve `GET /metrics`.
- Add `/api/v1` route namespace.
- Add structured JSON response envelope.
- Add stable `ApiError` response shape.
- Define global request body size limit.
- Decide JWT signing algorithm for the first pass.
- Record future JWT upgrade path.
- Keep signing secret/key out of source.
- Add JWT model rows and docs.
- Add bcrypt password hashing contract through `standard.bcrypt`.
- Enforce bcrypt 72-byte password limit as contract.
- Store password hash, cost, and `password_updated_at` in schema plan.
- Add role/scope authorization helper contract.
- Create `server/src/persistence.sem`.
- Create SQLite schema plan and schema SQL artifact.
- Add uniqueness constraints and replay/audit/request indexes.
- Add schema version table.
- Add explicit schema initialization artifact.
- Create `server/src/middleware.sem`.
- Add structured application log contract.
- Add durable audit event helper contract.
- Implement metrics contract for the bootstrap/runtime-gap counters.
- Add external Python API harness for server routes.

Not safe to mark fully complete yet:

- Generated request ids when `X-Request-Id` is absent. The scaffold uses a stable
  fallback string until secure random/string formatting is available in route
  middleware.
- Method-not-allowed/not-found for arbitrary paths. The native dispatcher owns
  unmatched route behavior; `apiNotFoundHandler` exists only as an explicit route.
- Body-size enforcement for future dynamic write routes. Registered write routes
  check length today.
- Full idempotency enforcement. Registered command writes require the header,
  but request hashing, replay lookup, conflict detection, and transactional
  writes are not executable yet.
- Auction/chat dynamic handlers. Route-param extraction exists, but handlers and
  persistence integration are not registered yet.
- Request duration measurement and structured per-route logs. Contract fields
  are declared, but executable logging is blocked on clock and structured
  logging composition.
- Production auth hardening. Demo auth endpoints execute with HS256 JWT
  verification and process-local hashed refresh-token rotation, but durable
  user/session storage, secret loading, runtime-clock claim validation, rate
  limiting, and auth audit rows remain open.
- Transaction helper, rollback behavior, and startup schema readiness check.
  Schema text exists, but the runner is not wired.
