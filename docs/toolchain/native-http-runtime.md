# Native HTTP Runtime

SemanticScript currently ships a small native blocking HTTP/1.1 adapter under
`SemanticScript/runtime/native_http/`. H2O / `libh2o` remains the planned
HTTP/2-capable backend once the Windows build/toolchain issues are resolved.
H2O is a C HTTP server/library with HTTP/1.x and HTTP/2 support and an MIT
license. The upstream FAQ documents `libh2o` as the library form, requiring
libuv 1.0+ and OpenSSL 1.0.2+ for library builds. Upstream install docs also
require CMake, pkg-config, zlib, and recursive source submodules.

Sources:

- https://github.com/h2o/h2o
- https://h2o.examp1e.net/faq.html
- https://h2o.examp1e.net/install.html
- https://powerdns.org/libh2o/

## Repo Layout

- `third_party/h2o` is a Git submodule pinned to an upstream H2O commit.
- SemanticScript-owned adapter code should live outside the submodule, likely
  under `SemanticScript/runtime/native_http/`.
- Compiler integration should stay in `SemanticScript/compiler/semsc.py` until
  runtime backend selection becomes large enough to split.

## Future H2O Integration Shape

H2O's `examples/libh2o/simple.c` shows the basic library model:

1. Initialize `h2o_globalconf_t`.
2. Register a host with `h2o_config_register_host`.
3. Register paths with `h2o_config_register_path`.
4. Allocate `h2o_handler_t` with `h2o_create_handler`.
5. Set `handler->on_req` to a C callback.
6. In callbacks, inspect `h2o_req_t`, set `req->res.status`, add headers, and
   send data with `h2o_send` or `h2o_send_inline`.
7. Initialize `h2o_context_t`.
8. Accept sockets and call `h2o_accept`.
9. Run either the libuv loop or H2O's evloop.

SemanticScript should wrap H2O with the same generated route table and generic
handler ABI used by the current adapter.

## Proposed SemanticScript ABI

Initial handler ABI:

```c
typedef struct SSHttpRequest SSHttpRequest;
typedef struct SSHttpResponse SSHttpResponse;

typedef int (*SSRouteHandler)(SSHttpRequest *request, SSHttpResponse *response);
```

Compiler lowering:

```text
operation healthHandler
input healthHandler request HttpRequest
input healthHandler response HttpResponse
output healthHandler CSignedInt32
```

Unlike console/library mode, `HttpRequest` and `HttpResponse` are not dropped as
opaque dependency inputs. For routed `target webServer` programs, the compiler
lowers them as pointer parameters.

## Runtime Adapter Responsibilities

The current adapter should:

- own socket initialization and shutdown;
- map `webServer`, `serverHost`, `serverPort`, and `route` metadata into an
  exact method/path dispatch table;
- translate the native request into `SSHttpRequest`;
- translate `SSHttpResponse` into HTTP status and body bytes;
- expose C functions for SemanticScript call targets such as
  `http.responseText`, `http.responseJson`, `http.requestPath`, and
  `http.requestMethod`;
- start with synchronous handlers and add async continuation support later.

The current adapter is blocking and single-threaded. It accepts and dispatches
one request path through the server loop at a time, so handlers and middleware
must not assume parallel request execution or preemptive route timeouts.

The future H2O adapter should additionally map generated route metadata into
H2O host/path registrations, translate `h2o_req_t`, keep request-scoped
allocations inside H2O request pools where possible, and expose response header
support such as `http.responseHeader`.

## Compiler Work Items

Done for the current native adapter:

1. Routed `target webServer` emits a native `main` instead of a stub.
2. `HttpRequest` and `HttpResponse` inputs are preserved in the handler ABI.
3. A route table is generated from `webServer` / `route` metadata.
4. `--emit-exe` links the SemanticScript-owned adapter library.
5. `semlint.py` reports unsupported routed handler ABI and malformed native
   response calls.
6. The blocking adapter exposes request method, path, header, raw query
   parameter, bounded body text, response text, and response header calls.
7. One path-scoped `routeMiddleware` callback can run before each matching
   route handler.

Remaining work:

1. Add `--runtime-backend h2o` or `--target-runtime h2o`.
2. Teach `--emit-exe` to link H2O outputs behind that backend flag.
3. Add path parameter APIs and a route-pattern matcher.
4. Add structured request body decoders and binary/streaming body APIs.
5. Enforce `routeTimeout` metadata without unsafe handler preemption.
6. Add a static-file helper with path traversal protection.
7. Add graceful shutdown hooks.
8. Add HTTP/2 over TLS once certificate and ALPN setup are wired.

## Build Plan

Proof-of-concept build:

```powershell
git submodule update --init --recursive third_party/h2o
cmake -S third_party/h2o -B third_party/h2o/build -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build third_party/h2o/build --target libh2o-evloop
```

The evloop target avoids requiring libuv in the first SemanticScript adapter.
TLS / browser HTTP/2 should use the normal `libh2o` path with OpenSSL and ALPN
once the plain HTTP path is stable.

Current local Windows result:

- `SemanticScript/runtime/native_http` builds with clang, Ninja, and
  `llvm-rc`.
- The default adapter backend now serves blocking HTTP/1.1 exact routes through
  native sockets and is covered by `apps/http-runtime-gauntlet/scripts/test_http_runtime_gauntlet.py`.
- TaskForge Web additionally verifies the application path through HTML pages,
  static assets, auth/session flow, sqlite persistence, and JSON APIs with
  `python apps/taskforge-web/scripts/test_taskforge_web.py`.
- H2O configures with local OpenSSL/zlib and `DISABLE_LIBUV=ON`.
- H2O's `libh2o-evloop` build requires Unix-like shell tools for generated
  headers; Git for Windows supplies `sh`, `perl`, and `sed`.
- After shell tools are available, the native MSVC/clang build stops because
  upstream H2O dependencies include `<pthread.h>` from `deps/cloexec`,
  `deps/libyrmcds`, and several H2O headers. This machine does not currently
  have a pthreads development package for the native Windows toolchain.

Working adapter build:

```powershell
cmake -S SemanticScript/runtime/native_http -B SemanticScript/runtime/native_http/build -G Ninja `
  -DCMAKE_C_COMPILER="C:/Program Files/LLVM/bin/clang.exe" `
  -DCMAKE_RC_COMPILER="C:/Program Files/LLVM/bin/llvm-rc.exe"
cmake --build SemanticScript/runtime/native_http/build
```

Working native webserver smoke:

```powershell
python apps/http-runtime-gauntlet/scripts/test_http_runtime_gauntlet.py
python apps/taskforge-web/scripts/test_taskforge_web.py
```

Backend options from here:

1. Build H2O through MSYS2/MinGW or WSL, where pthreads and shell tooling are
   normal.
2. Add a native Windows pthreads package and keep the clang/MSVC toolchain.
3. Keep H2O unpatched as a submodule and wire `semsc.py` to the adapter ABI
   first, then switch the adapter implementation from stub to H2O once the
   backend build is available.

## MVP

1. `target webServer` with a single `GET /health` route.
2. Native executable starts on `127.0.0.1:<port>`.
3. Route handler returns `200 text/plain`.
4. Test harness launches the process, calls it with `curl`, and terminates it.
5. HTTP/1.1 passes first; HTTP/2 over TLS follows once certificate and ALPN
   setup are wired.

## Risks

- H2O is heavier than the earlier CivetWeb option, but it is the stronger HTTP/2
  base.
- Windows builds may need careful OpenSSL/zlib/pkg-config setup.
- Handler APIs must keep response memory alive until H2O has sent it.
- HTTP/2 exposes concurrency immediately; the first SemanticScript adapter
  should either complete responses synchronously or explicitly retain request
  state for async work.
