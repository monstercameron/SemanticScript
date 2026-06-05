# Native HTTP Client API

Runtime outbound HTTP is separate from build-time `dependencyFetch`.
Application source should use a client namespace such as `net.fetchText` from
`standard.net`; it must not reuse server-side `http.request*` or
`http.response*` names. In the current compiler this surface has prototype
lowering: `net.fetch*` emits calls to the native HTTP client ABI and links the
native HTTP client plus native async sources, while real network behavior still
requires the opt-in libcurl/libuv runtime build.

## MVP Source Shape

```semanticscript
import net standard.net

operation fetchExample
output operation fetchExample Result HttpClientBodyText HttpClientErrorCode
effect fetchExample write network.http.client
useCapability fetchExample networkHttpClient
async fetchExample yes

call fetchCall net.fetchText
argument fetchCall request HttpGetRequest request
timeout fetchCall 3000ms
start fetchCall

await fetchCall
bind ok response HttpTextResponse fetchCall
bind error fetchError HttpClientErrorCode fetchCall
branch error source fetchCall target fetchFailed
fieldGet responseStatus HttpClientStatusCode response status
fieldGet responseBody HttpClientBodyText response body
defer releaseResponseBody net.freeTextBody responseBody
return ok responseBody
```

Build the request explicitly before the call:

```semanticscript
new request HttpGetRequest
fieldSet request url exampleUrl
fieldSet request policy.timeoutMillis timeoutMillis
fieldSet request policy.maxBodyBytes maxBodyBytes
fieldSet request policy.redirectLimit redirectLimit
```

The request record is intentional: timeout, response body limit, and redirect
limit are source-visible policy. The response record is also intentional: HTTP
404/500 status codes are transport successes, so status belongs in the ok value
instead of being hidden behind the transport error channel.

The intended async behavior is:

1. `start fetchCall` creates a future and starts outbound work.
2. Local work between `start` and `await` continues on the current operation.
3. `await fetchCall` pauses this operation and yields to the runtime.
4. The event loop runs other ready work.
5. Fetch completion resumes this operation after the `await`.

The current 1.0 compiler does not perform this continuation lowering by
default. The libuv backend is an opt-in experiment until the compiler's async
frame generation is complete. Today `net.fetch*` links `native_http_client` and
`native_async`, but the default native build remains a runtime-unavailable stub
unless libcurl/libuv are enabled.

## Native Prototype

The native prototype lives in
`SemanticScript/runtime/native_http_client/`.

- The blocking layer wraps libcurl for HTTP, HTTPS, redirects, TLS defaults,
  headers, and bounded response buffering.
- The async layer schedules the blocking layer through
  `SemanticScript/runtime/native_async/` using libuv work items.
- The later scalable layer should drive libcurl `multi_socket` with
  `uv_poll_t` without changing the public SemanticScript source API.

## Effects

Outbound fetch operations must declare:

```semanticscript
effect OP write network.http.client
```

Wrappers around fetch operations must re-export that effect through their public
contract tape so callers do not hide network authority behind ordinary helper
operations.

## Error Model

The native prototype reserves `HttpClientErrorCode` values for:

- invalid or missing request configuration;
- runtime backend unavailable;
- backend transport failure;
- cancellation;
- timeout;
- response body too large;
- TLS backend unavailable;
- unsupported scheme.

HTTP non-2xx statuses are transport successes. Callers should inspect the
response status when application-level status handling matters.
