# Native HTTP Client Runtime Adapter

This adapter is the SemanticScript-owned outbound HTTP client boundary. Source
code should call backend-neutral targets such as `net.fetchText`; generated code
should lower those calls to this C ABI only when the runtime fetch feature is
selected.

The canonical SemanticScript surface is request/response shaped:
`net.fetchText` takes an `HttpGetRequest` record and returns an
`HttpTextResponse` record. The C ABI remains lower-level and copy/out-param
based so generated code can choose the exact ownership path.

The prototype has two layers:

- blocking request/response helpers around libcurl;
- async fetch helpers that schedule the blocking helper through
  `SemanticScript/runtime/native_async/` using libuv work items.

Default CMake builds a stub that reports runtime-unavailable. Enable real
behavior explicitly:

```powershell
cmake -S SemanticScript/runtime/native_http_client -B SemanticScript/runtime/native_http_client/build `
  -DSEM_ASYNC_WITH_LIBUV=ON `
  -DSEM_HTTP_CLIENT_WITH_CURL=ON
cmake --build SemanticScript/runtime/native_http_client/build
```

When libuv or libcurl are not already installed, CMake fetches and builds pinned
upstream sources by default. Pass `-DSEM_ASYNC_FETCH_LIBUV=OFF` or
`-DSEM_HTTP_CLIENT_FETCH_CURL=OFF` to require system/package-manager installs.

The local benchmark target exercises the real async fetch path against the
deterministic test server:

```powershell
python experiments/libuv-fetcher/scripts/local_fetch_server.py --port 8765
.\SemanticScript\runtime\native_http_client\build\Release\sem_http_client_bench_demo.exe `
  http://127.0.0.1:8765/ 1000 16 64 3000
```

Arguments are URL, measured request count, concurrency, warmup request count,
and per-request timeout in milliseconds. The benchmark verifies every response
status, body, and body length before reporting throughput.

The first async implementation intentionally uses `uv_queue_work` plus libcurl's
easy API. That gives SemanticScript a concrete future/await experiment without
hand-writing DNS, TLS, redirects, or HTTP parsing. A later scalable backend
should drive libcurl's `multi_socket` API with `uv_poll_t`, keeping the public
ABI unchanged.

Ownership rules:

- `SSHttpClientRequest` is caller-owned and freed with
  `ss_http_client_request_free`.
- `SSHttpClientResponse` is runtime-owned after execute/fetch and freed with
  `ss_http_client_response_free`.
- `SSHttpFetchFuture` owns its request, timer, and response until
  `ss_http_client_fetch_free`.
- Pointers returned by body/header readers remain valid only until the owning
  response/future is freed.

Security defaults:

- unsupported schemes are rejected before network access;
- TLS verification is enabled when libcurl is active;
- response bodies are bounded before each realloc;
- redirects are bounded by a request setting.
