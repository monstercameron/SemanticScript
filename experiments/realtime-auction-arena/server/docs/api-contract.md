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

Idempotency keys are scoped by method, canonical route pattern, and authenticated
actor. A replay with the same scoped key and same canonical request hash returns
the original status and envelope. A replay with a different request hash returns
`idempotency_conflict`.

Observability contract:

- `GET /metrics` currently emits Prometheus-style bootstrap series.
- Planned request metrics use bounded route-pattern labels, not raw paths.
- Structured request logs use `http.request.start` and `http.request.finish`
  events with request id, route pattern, status, actor id, duration, and error
  code.
- Audit events are durable `audit_events` rows once persistence is wired, and
  never store raw credentials, tokens, cookies, or password hashes.

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
| GET | `/api/v1/auctions` | executable empty list |
| POST | `/api/v1/auctions` | executable fail closed |

Dynamic route contracts live in `src/routes.sem` and become executable once
their auction/chat handlers are registered and backed by persistence.
