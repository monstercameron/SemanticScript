# Native HTTP API

This is the source-level API for SemanticScript web servers backed by
the native HTTP runtime adapter in `SemanticScript/runtime/native_http/`.

The design rule is simple: SemanticScript code describes servers, routes,
request reads, and response writes. It does not mention H2O, libuv, sockets, or
event-loop internals. The compiler lowers those semantic records into the
adapter C ABI.

## Status

Current implementation status:

- `webServer`, `serverHost`, `serverPort`, and `route` are parsed and indexed.
- Routed `target webServer` programs emit a native `main` that calls the
  SemanticScript HTTP runtime adapter.
- The SemanticScript-owned C adapter ABI compiles.
- The default adapter backend serves blocking HTTP/1.1 exact routes.
- Request method, path, header, query parameter, bounded body-text, bounded
  body-byte, and multipart part reads are available through native runtime
  calls.
- Response text, response bytes, one-shot SSE event bodies, and custom response
  headers are available through native runtime calls.
- `routeMiddleware` executes one path-scoped middleware operation before the
  route handler. Middleware operations return the built-in `MiddlewareControl`
  enum, so they can either continue to the route handler or short-circuit after
  writing a complete response.
- The default adapter is blocking and single-threaded today. A long-running
  route handler, middleware operation, or future blocking outbound fetch pins
  the server loop until it returns or the process is stopped.
- H2O/HTTP2 dispatch is not wired into `semsc.py` yet.

This file describes the API shape implemented by the current adapter plus the
nearby request/response gaps still needed for a fuller web runtime.

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
- The first backend should support exact static paths. Path parameters can be
  added after the exact-route dispatcher is stable.
- Current checked methods are `GET`, `HEAD`, `POST`, `PUT`, `PATCH`, `DELETE`,
  and `OPTIONS`. Keep source methods uppercase unless a test explicitly covers
  compatibility behavior.
- `routeMiddleware SERVER PATH HANDLER` currently attaches one middleware
  operation to all methods on an exact path.
- `routeTimeoutOptOut SERVER PATH "rationale"` and
  `routeMiddlewareOptOut SERVER PATH "rationale"` declare intentional per-path
  gaps for linter coverage.
- `routeTimeout SERVER PATH DURATION` is parsed as metadata only. The blocking
  runtime does not preempt synchronous handlers.

## Handler ABI

The first compiled handler ABI should be explicit pointer-in, status-out:

```semanticscript
operation healthHandler
input healthHandler request HttpRequest
input healthHandler response HttpResponse
output healthHandler CSignedInt32
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
output tracingMiddleware MiddlewareControl
```

The compiler pre-registers `MiddlewareControl` as a `CSignedInt32`-backed enum
with `continueMiddlewareControl` and `shortCircuitMiddlewareControl`. Returning
`continueMiddlewareControl` runs the route handler. Returning
`shortCircuitMiddlewareControl` skips the handler and sends the response already
written by the middleware. A short-circuit middleware must write status, body,
and content type before it returns; the runtime turns a short-circuit with no
body into a visible 500 response instead of silently succeeding.

Later syntax can allow `output OP HttpResponse`, but the first backend should
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
const healthBody CNullTerminatedByteString "ok\n"

call writeHealthResponse http.responseText
arg writeHealthResponse response response
arg writeHealthResponse status HttpStatus.Ok
arg writeHealthResponse body healthBody
run writeHealthResponse
bind writeStatus CSignedInt32 writeHealthResponse
returnValue writeStatus
```

Initial call targets:

| Target | Inputs | Output | Lowering |
|---|---|---|---|
| `http.responseText` | `response HttpResponse`, `status HttpStatus`, `body CNullTerminatedByteString`, optional `contentType CNullTerminatedByteString` | `CSignedInt32` | `ss_http_response_text` |
| `http.responseBytes` | `response HttpResponse`, `status HttpStatus`, `body COpaqueMemoryAddress`, `bodyLength CByteCount`, optional `contentType CNullTerminatedByteString` | `CSignedInt32` | `ss_http_response_bytes` |
| `http.responseSseEvent` | `response HttpResponse`, `status HttpStatus`, `event CNullTerminatedByteString`, `data CNullTerminatedByteString` | `CSignedInt32` | `ss_http_response_sse_event` |
| `http.responseHeader` | `response HttpResponse`, `name CNullTerminatedByteString`, `value CNullTerminatedByteString` | `CSignedInt32` | `ss_http_response_header` |
| `http.requestMethod` | `request HttpRequest` | `CNullTerminatedByteString` | `ss_http_request_method` |
| `http.requestPath` | `request HttpRequest` | `CNullTerminatedByteString` | `ss_http_request_path` |
| `http.requestHeader` | `request HttpRequest`, `name CNullTerminatedByteString` | `CNullTerminatedByteString` | `ss_http_request_header` |
| `http.requestQueryParam` | `request HttpRequest`, `name CNullTerminatedByteString` | `CNullTerminatedByteString` | `ss_http_request_query_param` |
| `http.requestBodyText` | `request HttpRequest` | `CNullTerminatedByteString` | `ss_http_request_body_text` |
| `http.requestBodyBytes` | `request HttpRequest` | `COpaqueMemoryAddress` | `ss_http_request_body_bytes` |
| `http.requestBodyLength` | `request HttpRequest` | `CByteCount` | `ss_http_request_body_length` |
| `http.multipartPartText` | `request HttpRequest`, `name CNullTerminatedByteString` | `CNullTerminatedByteString` | `ss_http_multipart_part_text` |
| `http.multipartPartBytes` | `request HttpRequest`, `name CNullTerminatedByteString` | `COpaqueMemoryAddress` | `ss_http_multipart_part_bytes` |
| `http.multipartPartLength` | `request HttpRequest`, `name CNullTerminatedByteString` | `CByteCount` | `ss_http_multipart_part_length` |
| `http.multipartPartFilename` | `request HttpRequest`, `name CNullTerminatedByteString` | `CNullTerminatedByteString` | `ss_http_multipart_part_filename` |
| `http.multipartPartContentType` | `request HttpRequest`, `name CNullTerminatedByteString` | `CNullTerminatedByteString` | `ss_http_multipart_part_content_type` |

Current request-body behavior is deliberately bounded: the blocking adapter
buffers at most 64 KiB of headers plus body per request and returns `413` for
larger payloads. `requestBodyText` is for UTF-8/text demos. `requestBodyBytes`
and `responseBytes` preserve embedded NUL bytes by carrying an explicit length,
but the whole request is still buffered before handler dispatch.

Current multipart behavior is a small `multipart/form-data` boundary parser for
bounded requests. It can read a named part's text, bytes, byte length, filename,
and content type. It does not stream files to disk, decode nested multipart
bodies, percent-decode names, or enforce per-part quotas beyond the request cap.

Nullable request readers are still pointer-shaped at the ABI boundary:
`http.requestHeader`, `http.requestQueryParam`, `http.requestCookie`,
`http.requestBodyText`, `http.requestBodyBytes`, and multipart part readers can
return `NULL` when the named value is absent, empty, or over the bounded request
limit. Passing that result directly to a non-null response writer currently
makes the handler fail. Production handlers should guard nullable reader results
with `pointer.isNull` and branch to an explicit response. Routes that
intentionally pin the adapter's null-body 500 path for regression coverage
should use `pinsNullBodyFailurePath OP "rationale"` rather than a prose warning.

Current SSE behavior is one-shot event-stream body formatting through
`http.responseSseEvent`. It emits a valid `text/event-stream` payload with a
fixed `Content-Length` and then the blocking adapter closes the connection.
Long-lived SSE streams, incremental writes, flush, cancellation, and keep-alive
heartbeats remain future streaming APIs.

Current query behavior is raw splitting by `&` and `=`. The blocking adapter's
lookup returns the first matching duplicate key today. Percent decoding,
structured form parsing, and a language-level duplicate-key policy are future
APIs.

Second-wave targets:

| Target | Purpose |
|---|---|
| `http.responseJson` | Set status, `application/json`, and body. |
| `http.responseStreamStart` / `http.responseStreamWrite` / `http.responseStreamEnd` | Long-lived streaming responses for SSE and large downloads. |
| `http.pathParam` | Read a value captured by a route pattern such as `/todos/:todoId`. |
| `http.staticFile` | Serve a file through a safe static-file helper. |
| `http.requestShutdown` | Coordinate graceful server shutdown. |

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
input healthHandler request HttpRequest
input healthHandler response HttpResponse
output healthHandler CSignedInt32
effect healthHandler read http.request.method
effect healthHandler read http.request.path
effect healthHandler write http.response
memory healthHandler arena request
async healthHandler no
useCapability healthHandler httpRequestReader
useCapability healthHandler httpResponseWriter
purpose healthHandler "Return a plain health-check response"

call methodReadCall http.requestMethod
arg methodReadCall request request
run methodReadCall
bind requestMethod CNullTerminatedByteString methodReadCall

call pathReadCall http.requestPath
arg pathReadCall request request
run pathReadCall
bind requestPath CNullTerminatedByteString pathReadCall

const healthBody CNullTerminatedByteString "ok\n"
call responseWriteCall http.responseText
arg responseWriteCall response response
arg responseWriteCall status HttpStatus.Ok
arg responseWriteCall body healthBody
run responseWriteCall
bind responseWriteStatus CSignedInt32 responseWriteCall
returnValue responseWriteStatus
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
HttpResponse] -> CSignedInt32`. `semlint.py` carries the name-level and
middleware-level contracts on top: canonical input names are `request` and
`response`, middleware bound through `routeMiddleware` must declare
`MiddlewareControl`, and response-body wrappers must declare
`responseBodyForwarder OP bodyInputName` so nullable-body checks remain
transitive.
