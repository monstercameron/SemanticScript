# Native HTTP API

This is the source-level API for SemanticScript web servers backed by
the native HTTP runtime adapter in `SemanticScript/runtime/native_http/`.

The design rule is simple: SemanticScript code describes servers, routes,
request reads, and response writes. It does not mention H2O, libuv, sockets, or
event-loop internals. The compiler lowers those semantic records into the
adapter C ABI.

## Status

Current implementation status:

- `webServer`, `serverHost`, `serverPort`, `route`, and `staticRoute` are
  parsed and indexed.
- Routed `target webServer` programs emit a native `main` that calls the
  SemanticScript HTTP runtime adapter.
- The SemanticScript-owned C adapter ABI compiles.
- The default adapter backend serves blocking HTTP/1.1 route handlers and
  declarative static-file prefixes.
- Request method, path, header, query parameter, bounded body-text, bounded
  body-byte, and multipart part reads are available through native runtime
  calls.
- Response text, response bytes, one-shot SSE event bodies, and custom response
  headers are available through native runtime calls.
- `standard.http` exposes blocking SSE stream wrappers and
  `serverIsShuttingDown` as ordinary stdlib operations backed by generic native
  `runtimeBinding` hooks.
- `routeMiddleware` executes one path-scoped middleware operation before the
  route handler. Middleware operations return the built-in `MiddlewareControl`
  enum, so they can either continue to the route handler or short-circuit after
  writing a complete response.
- The default adapter is blocking and single-threaded today. A long-running
  route handler, middleware operation, or future blocking outbound fetch pins
  the server loop until it returns or the process is stopped.
- H2O/HTTP2 dispatch is not wired into `semsc.py` yet. The source-level
  `SEM_HTTP_WITH_H2O` branch is a staged backend hook only; `sem` exposes this
  as the disabled `nativeHttpH2oBackend` runtime feature and the branch returns
  `SS_HTTP_ERR_RUNTIME_UNAVAILABLE`.

This file describes the API shape implemented by the current adapter plus the
nearby request/response gaps still needed for a fuller web runtime.

## Concurrency Limits And Testing (read before load-testing)

The default adapter is **blocking and single-threaded**: it accepts one
connection, serves a single request on it (it always responds with
`Connection: close`), closes, and only then accepts the next. Under concurrent
or slow clients this bites in practice — firing several requests at once
(especially with some hitting a timeout) can leave sockets lingering and the
server stops answering *everything*, including `/health`. Recovery is kill +
restart, then one request at a time. This is expected for the current backend; a
non-blocking/H2O backend is future work. `sem docs search "concurrent dispatch"`
returns the disabled `nativeHttpConcurrentDispatch` runtime feature so tools do
not infer concurrency from the `webServer` surface.

A dropped client connection no longer kills the server: the adapter ignores
`SIGPIPE` on POSIX, so a client that closes/resets mid-response (keep-alive
churn, a browser favicon probe, or a client that gives up on a slow handler)
makes `send()` return an error and unwind cleanly instead of terminating the
process. On Windows `send()` already returns `WSAECONNRESET` there. Even so, do
not load-test the blocking adapter concurrently.

Testing guidance (especially on Windows):

- **Serialize requests** — one at a time, with `Connection: close` and a
  generous timeout. Do not fan out parallel or keep-alive bursts against the
  blocking adapter.
- **Use `curl`, not `Invoke-WebRequest`.** On Windows PowerShell 5.1,
  `Invoke-WebRequest` may route `127.0.0.1` through a system proxy and report a
  bare "Unable to connect" with no useful error. `curl --noproxy '*' http://127.0.0.1:PORT/...`
  surfaces the real response (including a server-side fault on stdout).
- **Capture stdout/stderr** (`server.exe > out.txt 2>&1`) so a handler fault
  (`SSRUN002`) is visible. A crash presents as "connection refused" on every
  *subsequent* connect (the process died at the TCP layer looks identical to a
  bind problem). Confirm liveness with `Get-Process` before chasing networking.
- **Register `routeNotFound`** (and usually `routeMethodNotAllowed`). A browser
  auto-requests `/favicon.ico` and other assets; without a not-found handler
  those hit the default 404 path and add connection churn. An explicit handler
  keeps unmatched paths cheap and predictable.
- **Persisting a server across separate tool calls / agent steps.** A process a
  tool shell spawns (`Start-Process`, `&`) is reaped when that shell exits, so
  the server dies between calls. To keep one alive out-of-band on Windows,
  launch it parented to the WMI service:
  `Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{CommandLine='C:\path\server.exe'}`.
  Native webServer entrypoints switch the process working directory to the
  executable directory at startup, so relative SQLite paths and `staticRoute`
  roots resolve beside the exe even when the launcher starts elsewhere.

## SQLite Process-Lifetime Handles

Handlers do not need to open and close SQLite on every request when the app can
share one process-lifetime handle. Use the server lifecycle rows for ownership:
open the database from `webServerStartup`, store the resulting `SqliteDatabase`
in `storage module mutable` or `sharedState process mutable`, read that handle
from route handlers, and close it from `webServerShutdown`.

The shape is:

```semanticscript
storage module mutable appDatabase SqliteDatabase 0

operation openAppDatabase
call openDatabaseCall sqlite.openDatabase
argument openDatabaseCall path String databasePath
argument openDatabaseCall mode SqliteOpenMode readWriteCreateSqliteOpenMode
run openDatabaseCall
bind ok openedDatabase SqliteDatabase openDatabaseCall
bind error openDatabaseError SqliteDatabaseOpenFailure openDatabaseCall
branch error source openDatabaseCall target openFailed
set storage appDatabase openedDatabase
return value startupOkStatus

operation closeAppDatabase
call closeDatabaseCall sqlite.closeDatabase
argument closeDatabaseCall database SqliteDatabase appDatabase
run closeDatabaseCall
ignore ok source closeDatabaseCall type Int32
bind error closeDatabaseError SqliteDatabaseCloseFailure closeDatabaseCall
return value shutdownOkStatus
```

This is not a connection pool. It is one handle reused by a single native
process. That matches the current blocking, single-threaded HTTP adapter. If a
future backend dispatches handlers concurrently, sharing this handle needs an
explicit guard/owner contract or a real pool; otherwise keep the per-request
open/close pattern for isolation.

## Server Shape

MVP server metadata uses the existing line forms:

```semanticscript
project HealthServer
target webServer
runtime native 1

webServer healthServer
serverHost healthServer "127.0.0.1"
serverPort healthServer 8080
route healthServer GET "/health" healthHandler
```

Rules:

- `target webServer` selects the HTTP entry generator.
- `webServer NAME` creates one server boundary.
- `serverHost SERVER "HOST"` sets the bind host.
- `serverPort SERVER PORT` sets the bind port.
- `route SERVER METHOD PATH HANDLER` maps one HTTP method/path pair to one
  operation.
- `staticRoute SERVER URL_PREFIX ROOT_DIRECTORY` maps GET/HEAD requests under
  one URL prefix to files under a public root directory without writing a
  handler. For example, `staticRoute appServer "/assets" "assets"` serves
  `/assets/site.css` from `assets/site.css` and `/assets` from
  `assets/index.html` beside the executable.
- `routeNotFound SERVER HANDLER` registers a JSON/HTML/application fallback for
  unmatched paths.
- `routeMethodNotAllowed SERVER HANDLER` registers the fallback used when a
  request path matches a route pattern but the HTTP method does not.
- Route paths can be exact literals or contain path-parameter segments in
  either `:name` or `{name}` form. Regex and constraint forms such as
  `{id:[0-9]+}` are rejected; the native matcher only captures whole path
  segments by name. Static routes are prefix routes and are checked before
  handler routes.
- Current checked methods are `GET`, `HEAD`, `POST`, `PUT`, `PATCH`, `DELETE`,
  and `OPTIONS`. Keep source methods uppercase unless a test explicitly covers
  compatibility behavior.
- `routeMiddleware SERVER PATH HANDLER` currently attaches one middleware
  operation to all methods on an exact path.
- `routeTimeoutOptOut SERVER PATH "rationale"` and
  `routeMiddlewareOptOut SERVER PATH "rationale"` declare intentional per-path
  gaps for linter coverage.
- `routeTimeout SERVER PATH DURATION` is parsed as metadata only. The blocking
  runtime does not preempt synchronous handlers; `semlint` SS3618 warns on the
  row so the limitation is visible during `sem check`.

## HTML Template Islands And Inline JavaScript

`html body template` scans ordinary text and quoted attributes for `{{name}}`
hydrate holes. The old `{name}` hole form is a hard error; use `{{name}}`.
Single braces in JavaScript, CSS, and object literals remain literal unless
they are exactly the old hole syntax, so `import { initHTMLeX } from
"/assets/app.js"` does not become a template hole. Hydrating directly inside raw
script/style text is rejected by design; put dynamic values in normal HTML
text/attributes, a JSON endpoint, or a separate static/script route and have the
browser code fetch or read those values. URL-bearing attributes (`href`, `src`,
`action`, `formaction`, and `poster`) require `HtmlSafeUrl`; plain `String`
continues to escape in text and non-URL quoted attribute sinks, but is rejected
for those URL sinks.

For larger client scripts, prefer `staticRoute appServer "/assets" "assets"` or
a dedicated route returning a `String` constant. Keep script source as script
source, not as SemanticScript row syntax.

## Handler ABI

The first compiled handler ABI should be explicit pointer-in, status-out:

```semanticscript
operation healthHandler
input operation healthHandler request HttpRequest
input operation healthHandler response HttpResponse
output operation healthHandler Int32
effect healthHandler write http.response
memory healthHandler arena request
async healthHandler no
```

`HttpRequest` and `HttpResponse` are opaque SemanticScript handles. For
`target webServer`, the compiler must preserve them as pointer parameters
instead of dropping them as ordinary opaque metadata inputs.

Generated C-compatible handler shape:

```c
int healthHandler(SSHttpRequest *request, SSHttpResponse *response);
```

Return values:

```text
0  handled successfully
1  handler configuration error
2  runtime unavailable
3  native engine error
```

Middleware operations use the same request/response input ABI but declare:

```semanticscript
output operation tracingMiddleware MiddlewareControl
```

The compiler pre-registers `MiddlewareControl` as a `Int32`-backed enum
with `continueMiddlewareControl` and `shortCircuitMiddlewareControl`. Returning
`continueMiddlewareControl` runs the route handler. Returning
`shortCircuitMiddlewareControl` skips the handler and sends the response already
written by the middleware. A short-circuit middleware must write status, body,
and content type before it returns; the runtime turns a short-circuit with no
body into a visible 500 response instead of silently succeeding.

Later syntax can allow `output operation OP HttpResponse`, but the first backend should
not hide response ownership. Writing into an explicit response handle makes the
LLVM ABI and response lifetime easier to inspect.

## Capabilities And Effects

Effects should describe request/response behavior the handler actually performs.
A static route that only writes a response does not need a request-read effect
just because it receives an `HttpRequest` handle.

Capability paths are hierarchical. A capability declared at `http.request read`
authorizes narrower request effects such as `read http.request.method`,
`read http.request.path`, and `read http.request.cancellationToken`. Use narrower
capabilities when a handler should only inspect one request edge.

## Response Calls

The first runtime calls should be direct and small:

```semanticscript
storage local immutable healthBody String "ok\n"
storage local immutable okStatus HttpStatusCode 200

call writeHealthResponseCall http.responseText
argument writeHealthResponseCall response HttpResponse response
argument writeHealthResponseCall status HttpStatusCode okStatus
argument writeHealthResponseCall body HttpTextBody healthBody
run writeHealthResponseCall
bind value writeStatus Int32 writeHealthResponseCall
return value writeStatus
```

`HttpStatusCode` is an `Int32`-backed role alias exported by `standard.http`;
`HttpTextBody` is a string-backed role alias. There is no predeclared
`HttpStatus.Ok` constant, so declare concrete values with `storage` and pass them by name.

Static assets do not need a handler operation when they fit the built-in
directory-serving contract. Use `staticRoute SERVER URL_PREFIX ROOT_DIRECTORY`;
the runtime strips the URL prefix, serves the remaining relative path with the
same safety checks and content-type sniffing as `http.responseFile`, maps the
prefix itself to `index.html`, and returns the standard plaintext 404 for a
missing file. Use a hand-written `route` + `http.responseFile` handler only
when application code must authenticate, rewrite, or audit the asset request.
Native static file responses now stamp `Cache-Control: public, max-age=60`,
`ETag`, and `Last-Modified`. `staticRoute` also honors exact
`If-None-Match` and `If-Modified-Since` validator matches with `304 Not
Modified`; hand-written handlers can still use the exported header constants
when they own a custom caching policy.

Initial call targets:

| Target | Inputs | Output | Lowering |
|---|---|---|---|
| `http.responseHtml` | `response HttpResponse`, `status HttpStatusCode`, `body HttpTextBody` | `Int32` | `ss_http_response_text` with `text/html; charset=utf-8` |
| `http.responseText` | `response HttpResponse`, `status HttpStatusCode`, `body HttpTextBody`, optional `contentType HttpContentType` | `Int32` | `ss_http_response_text` |
| `http.redirect` | `response HttpResponse`, `status HttpStatusCode`, `location HttpHeaderValue` | `Int32` | `ss_http_response_header(Location)` + `ss_http_response_text` with an empty `text/plain` body |
| `http.responseBytes` | `response HttpResponse`, `status HttpStatusCode`, `body HttpByteBody`, `bodyLength HttpBodyLength`, optional `contentType HttpContentType` | `Int32` | `ss_http_response_bytes` |
| `http.responseSseEvent` | `response HttpResponse`, `status HttpStatusCode`, `event SseEventName`, `data SseEventData` | `Int32` | `ss_http_response_sse_event` |
| `http.responseHeader` | `response HttpResponse`, `name HttpHeaderName`, `value HttpHeaderValue` | `Int32` | `ss_http_response_header` |
| `http.responseFile` | `response HttpResponse`, `status HttpStatusCode`, `rootDirectory String`, `requestedPath String` | `Int32` | `ss_http_response_file`; rejects traversal/absolute paths, sniffs content type by extension, refuses files over 16 MiB, and stamps Cache-Control/ETag/Last-Modified when file metadata is available |
| `http.requestMethod` | `request HttpRequest` | `HttpRequestValue` | `ss_http_request_method` |
| `http.requestPath` | `request HttpRequest` | `HttpRequestValue` | `ss_http_request_path` |
| `http.requestPathParam` | `request HttpRequest`, `name String` | `HttpRequestValue` | `ss_http_request_path_param` |
| `http.requestHeader` | `request HttpRequest`, `name String` | `HttpRequestValue` | `ss_http_request_header` |
| `http.requestCookie` | `request HttpRequest`, `name String` | `HttpRequestValue` | `ss_http_request_cookie` |
| `http.requestQueryParam` | `request HttpRequest`, `name String` | `HttpRequestValue` | `ss_http_request_query_param` |
| `http.requestBodyText` | `request HttpRequest` | `HttpTextBody` | `ss_http_request_body_text` |
| `http.requestBodyBytes` | `request HttpRequest` | `HttpByteBody` | `ss_http_request_body_bytes` |
| `http.requestBodyLength` | `request HttpRequest` | `HttpBodyLength` | `ss_http_request_body_length` |
| `http.requestValueLength` | `value HttpRequestValue` | `HttpBodyLength` | `ss_http_request_value_length`; returns `0` for null |
| `http.requestValueIsEmpty` | `value HttpRequestValue` | `Bool` | `ss_http_request_value_is_empty`; true for null or empty |
| `http.nowMillis` | none | `Int64` | `ss_http_now_millis` |
| `http.sessionExpiresAt` | `nowMillis Int64`, `ttlMillis SessionTtlMillis` | `SessionExpiresAtMillis` | `standard.http` runtimeBinding wrapper over `ss_http_session_expires_at`; links in native/webServer builds |
| `http.sessionIsExpired` | `nowMillis Int64`, `expiresAtMillis SessionExpiresAtMillis` | `Bool` | `standard.http` runtimeBinding wrapper over `ss_http_session_is_expired`; links in native/webServer builds |
| `http.multipartPartText` | `request HttpRequest`, `name String` | `HttpTextBody` | `ss_http_multipart_part_text` |
| `http.multipartPartBytes` | `request HttpRequest`, `name String` | `HttpByteBody` | `ss_http_multipart_part_bytes` |
| `http.multipartPartLength` | `request HttpRequest`, `name String` | `HttpBodyLength` | `ss_http_multipart_part_length` |
| `http.multipartPartFilename` | `request HttpRequest`, `name String` | `String` | `ss_http_multipart_part_filename` |
| `http.multipartPartContentType` | `request HttpRequest`, `name String` | `HttpContentType` | `ss_http_multipart_part_content_type` |
| `http.openSseStream` | `response HttpResponse`, `status HttpStatusCode` | `Int32` | `standard.http` runtimeBinding wrapper over `ss_http_sse_open` |
| `http.writeSseEvent` | `response HttpResponse`, `event SseEventName`, `data SseEventData` | `Int32` | `standard.http` runtimeBinding wrapper over `ss_http_sse_write_event` |
| `http.writeSseEventWithId` | `response HttpResponse`, `id SseEventId`, `event SseEventName`, `data SseEventData` | `Int32` | `standard.http` runtimeBinding wrapper over `ss_http_sse_write_event_with_id` |
| `http.writeSseHeartbeat` | `response HttpResponse`, `comment SseHeartbeatComment` | `Int32` | `standard.http` runtimeBinding wrapper over `ss_http_sse_heartbeat` |
| `http.closeSseStream` | `response HttpResponse` | `Int32` | `standard.http` runtimeBinding wrapper over `ss_http_sse_close` |
| `http.clientDisconnected` | `response HttpResponse` | `Bool` | `standard.http` runtimeBinding wrapper over `ss_http_client_disconnected` |
| `http.serverIsShuttingDown` | none | `Bool` | `standard.http` runtimeBinding wrapper over `ss_http_server_is_shutting_down` |

### Set-Cookie And TLS Detection

Cookies are emitted today with `http.responseHeader` and the exported
`standard.http` constants:

- `setCookieHeaderName` is the canonical `Set-Cookie` header name.
- `cookieSecureHttpOnlySameSiteLaxSuffix` is the production session-cookie
  suffix when the request is known to be HTTPS.
- `cookieHttpOnlySameSiteLaxSuffix` is the local/plain-HTTP suffix.
- `forwardedProtoHeaderName` and `forwardedProtoHttpsValue` are the documented
  proxy-header check for deployments behind a trusted TLS terminator.

The native HTTP/1.1 adapter does not terminate TLS and therefore cannot infer
the browser-facing scheme by itself. In production, terminate TLS before the
SemanticScript process and configure that ingress to strip any client-supplied
`X-Forwarded-Proto` header, then set `X-Forwarded-Proto: https` itself. Handler
code can read that header with `http.requestHeader`, guard the nullable result
with `pointer.isNull`, compare it to `forwardedProtoHttpsValue` with
`text.equals`, and choose the `Secure` cookie suffix only on the HTTPS branch.
Do not trust `X-Forwarded-Proto` from arbitrary direct clients.

Current request-body behavior is deliberately bounded: the blocking adapter
buffers at most 64 KiB of headers plus body per request and returns `413` for
larger payloads. `requestBodyText` is for UTF-8/text demos. `requestBodyBytes`
and `responseBytes` preserve embedded NUL bytes by carrying an explicit length,
but the whole request is still buffered before handler dispatch.

Form-urlencoded bodies use `http.requestBodyText` followed by `http.formField`.
`http.formField` URL-decodes one named field into caller-owned scratch memory;
it does not allocate its return value. Prefer `memory.allocateMemoryBytes` for
that scratch, branch on allocation failure with `pointer.isNull`, pass the
allocated pointer and capacity to `http.formField`, guard the returned
`HttpRequestValue` with `pointer.isNull`, and release the scratch with
`memory.releaseMemoryBytes` after all validation, authentication, rendering, or
persistence has finished. The returned value aliases the scratch buffer, so
freeing or overwriting the scratch before downstream use is a use-after-free or
stale-value bug.

Current multipart behavior is a small `multipart/form-data` boundary parser for
bounded requests. It can read a named part's text, bytes, byte length, filename,
and content type. It does not stream files to disk, decode nested multipart
bodies, percent-decode names, or enforce per-part quotas beyond the request cap.
Multipart readers operate directly on `HttpRequest` and do not use the
caller-owned scratch pattern. Form-urlencoded readers operate on
`HttpTextBody` and do use scratch. There is no unified `requestFormValue`
adapter yet; choose the reader family from the request `Content-Type` instead
of mixing the two surfaces.

JSON credential POST handlers should not pretend the body is form-urlencoded.
The supported pattern today is:

1. Read `http.requestBodyText` and branch on `pointer.isNull` before parsing.
2. Parse the body with `json.createDocument`, using an explicit
   `JsonCapacityBytes` bound suitable for login payloads.
3. Register `defer ... json.destroyDocument` immediately after the document is
   owned.
4. Use `json.documentRoot`, then `json.objectFieldAt` for fields such as
   `username` and `password`.
5. Copy each field with `json.cursorString` into caller-owned scratch buffers,
   branch on Result errors, then authenticate from those copied values.
6. Return JSON with `http.responseHeader Content-Type application/json` followed
   by `http.responseText`, or use the exported `jsonContentType` constant from
   `standard.http`.

That pattern keeps URL-decoding, JSON parsing, scratch-buffer ownership, and
document cleanup visible as source data. It also avoids the common mistake of
feeding a JSON login body to `http.formField`, which only understands
`application/x-www-form-urlencoded`.

Nullable request readers are still pointer-shaped at the ABI boundary:
`http.requestHeader`, `http.requestQueryParam`, `http.requestCookie`,
`http.requestBodyText`, `http.requestBodyBytes`, and multipart part readers can
return `NULL` when the named value is absent, empty, or over the bounded request
limit. Passing that result directly to a non-null response writer currently
makes the handler fail. Production handlers should guard nullable reader results
with `pointer.isNull` and branch to an explicit response. Routes that
intentionally pin the adapter's null-body 500 path for regression coverage
should use `pinsNullBodyFailurePath OP "rationale"` rather than a prose warning.
For scalar presence checks, call `http.requestValueIsEmpty` or
`http.requestValueLength` on the nullable value after reading it. Both helpers
treat `NULL` as empty, which is the intended cookie/session existence test
without a database lookup.

`http.responseSseEvent` remains the one-shot event-stream body formatter. It
emits a valid `text/event-stream` payload with a fixed `Content-Length` and then
the blocking adapter closes the connection.

Streaming SSE is exposed through `standard.http`, not compiler-specific
`http.sse*` targets. Import `standard.http` and call `http.openSseStream`,
`http.writeSseEvent`, `http.writeSseEventWithId`, `http.writeSseHeartbeat`,
`http.closeSseStream`, and `http.clientDisconnected`. Those operations are
standard-library wrappers over native `runtimeBinding` hooks. Route-level
fanout, async subscriber queues, request cancellation, and nonblocking
slow-client handling are still application or future runtime work.

Graceful shutdown drain state is exposed through `standard.http`, not through
application-specific compiler lowering. Import `standard.http` and call
`http.serverIsShuttingDown` from a handler or middleware that declares
`effect OP read http.server` and uses a capability covering `http.server read`.
The operation returns only the process drain flag. There is no built-in
graceful-drain timeout policy yet: application code owns whether that flag makes
readiness fail, command routes reject, SSE subscribers drain, or read-only
routes remain available, and an external supervisor/reverse proxy should own
hard shutdown deadlines.

Session expiry policy is explicit source data. Import `standard.http`, read the
current timestamp with `http.nowMillis`, compute a persisted expiry with
`http.sessionExpiresAt(nowMillis, sessionDefaultTtlMillis)`, and reject later
requests when `http.sessionIsExpired(currentNowMillis, storedExpiresAtMillis)`
returns true. `sessionDefaultTtlMillis` is 24 hours; applications can pass their
own immutable Int64 value through the `SessionTtlMillis` argument row when their
auth policy differs. Both helpers are native runtime bindings, so this direct
pattern links in native and webServer builds.

Current query behavior is splitting by `&` and `=`, then URL-decoding `%XX` and
`+` into the returned caller-visible value. The blocking adapter's lookup
returns the first matching duplicate key today. Structured form parsing and a
language-level duplicate-key policy are future APIs.

Future targets:

| Target | Purpose |
|---|---|
| Built-in request logger | Emit method/path/status/latency from the adapter without hand-written middleware. |
| Metrics/tracing surface | First-class counters, timings, spans, and structured application events. |
| Async stream fanout / cancellation hooks | Nonblocking subscriber queues, backpressure/queue-depth limits, and request-cancellation-aware long-lived SSE. |
| Request/connection cancellation token | Let long-running handlers and SSE fanout observe client disconnects and shutdown cancellation. |

## Minimal Example

```semanticscript
project HealthServer
target webServer
runtime native 1

webServer healthServer
serverHost healthServer "127.0.0.1"
serverPort healthServer 8080
route healthServer GET "/health" healthHandler

capability httpRequestReader http.request read
# invariant: Capability paths are hierarchical: http.request read authorizes method and path reads.
capability httpResponseWriter http.response write

operation healthHandler
input operation healthHandler request HttpRequest
input operation healthHandler response HttpResponse
output operation healthHandler Int32
effect healthHandler read http.request.method
effect healthHandler read http.request.path
effect healthHandler write http.response
memory healthHandler arena request
async healthHandler no
useCapability healthHandler httpRequestReader
useCapability healthHandler httpResponseWriter
purpose operation healthHandler "Return a plain health-check response"

call methodReadCall http.requestMethod
argument methodReadCall request HttpRequest request
run methodReadCall
bind value requestMethod String methodReadCall

call pathReadCall http.requestPath
argument pathReadCall request HttpRequest request
run pathReadCall
bind value requestPath String pathReadCall

storage local immutable healthBody String "ok\n"
storage local immutable okStatus HttpStatusCode 200
call responseWriteCall http.responseText
argument responseWriteCall response HttpResponse response
argument responseWriteCall status HttpStatusCode okStatus
argument responseWriteCall body HttpTextBody healthBody
run responseWriteCall
bind value responseWriteStatus Int32 responseWriteCall
return value responseWriteStatus
```

The `requestMethod` and `requestPath` reads are intentionally shown even though
the route table already matched them. They give diagnostics and agents concrete
source-level values to cite when a handler branches on request metadata.

## Compiler Lowering

For one server, `semsc.py` should generate:

1. Normal LLVM functions for every route handler.
2. External declarations for the adapter functions.
3. A native route table equivalent to:

```c
static SSHttpRoute ss_routes[] = {
    {"GET", "/health", healthHandler},
};
```

4. A server config equivalent to:

```c
static SSHttpServerConfig ss_server = {
    "127.0.0.1",
    8080,
    ss_routes,
    1,
};
```

5. A real `main` that returns `ss_http_server_run(&ss_server)`.

Compiler codegen validates the route handler ABI before emitting the native
route table: route handlers must compile to exactly `[HttpRequest,
HttpResponse] -> Int32`. `semlint.py` carries the name-level and
middleware-level contracts on top: canonical input names are `request` and
`response`, middleware bound through `routeMiddleware` must declare
`MiddlewareControl`, and response-body wrappers must declare
`responseBodyForwarder OP bodyInputName` so nullable-body checks remain
transitive.
