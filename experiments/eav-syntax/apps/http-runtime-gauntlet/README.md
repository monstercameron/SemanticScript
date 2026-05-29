# http-runtime-gauntlet (EAV port)

Full 1:1 EAV-Steps port of `apps/http-runtime-gauntlet` (the v0.1 SemanticScript
native-HTTP/1.1 conformance harness).

## Parity

- **27 operations** — 2 helpers (`addGauntletHeaders`, `writeTextResponse`),
  23 route handlers, 2 middleware — matching the original op count exactly.
- **1 `webServer` entity** with **24 routes** and **23 middleware bindings**,
  matching the original.
- **2 capabilities** (`httpRequestReader`, `httpResponseWriter`) and **7
  module-storage** constants, matching the original.
- **81 call entities** — the original's inline `call`/`argument`/`run`/`bind`
  records, promoted to first-class `call` entities (the §20 split).
- Every `http.*` request-read / response-write / multipart / SSE call and the
  `pointer.isNull` null-guards are converted.

## Conversions / language differences

- The v0.1 `webServer`/`serverHost`/`serverPort`/`route`/`routeMiddleware`
  keywords become the subject-anchored EAV `webServer` entity (`X is webServer`,
  `X host`, `X port`, `X route`, `X middleware`, §14).
- **Middleware** uses EAV's §14 ABI `(request, response, next NextMiddleware)
  -> Bool` instead of the v0.1 `MiddlewareControl` enum:
  `continueMiddlewareControl` → `Bool true` (continue),
  `shortCircuitMiddlewareControl` → `Bool false` (short-circuit). The
  `MiddlewareControl` enum and its constants disappear.
- **Effect coverage**: EAV `grants` are exact-match (no hierarchical path
  coverage), so `httpRequestReader` enumerates each narrower read sub-path
  (`http.request.method`/`.path`/`.header`/`.query`/`.body`/`.multipart`) that
  the v0.1 source covered via a single hierarchical `http.request read` grant.
- `warning` → the universal `risk` metadata predicate; the semsc-specific
  linter-contract verbs (`pinsNullBodyFailurePath`, `responseBodyForwarder`,
  `routeTimeoutOptOut`) become `rationale` rows (EAV has no SS3603/SS3602/route-
  timeout equivalents).
- `bind value`/`ignore value source` → `out NAME TYPE` / `discards "reason"`.

## Deferred execution

`target webServer` lowering is out of scope in v0.3 (§27), so the harness
parses + lints clean — handler ABIs validated (SS2603), route methods checked
(SS2601), routes exact-match-checked (SS2602), effect coverage clean — but is
**not** codegen'd (`lower_to_llvm` raises). When webServer lowering lands on the
WS3-017 HTTP runtime, each route becomes an executable golden with no source
changes.
