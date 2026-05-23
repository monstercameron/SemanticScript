# Native HTTP Runtime Adapter

This adapter is the SemanticScript-owned boundary between generated route
handlers and the selected native HTTP engine. The current default engine is a
small blocking HTTP/1.1 socket server used for exact-route development and
tests; `third_party/h2o` is reserved for the future HTTP/2-capable backend.

Current status:

- The public C ABI compiles as a standalone static library.
- The default backend is a small blocking HTTP/1.1 socket server for exact-route
  development and tests.
- The default backend now supports request method/path/header/query/body-text
  and body-byte reads, bounded multipart part reads, response text/bytes,
  one-shot SSE event bodies, response header writes, and one path-scoped
  middleware callback.
- The fallback accept loop installs process signal handlers for SIGINT/SIGTERM
  (and Windows console close/break events), polls the listen socket every
  250 ms, stops accepting new clients when shutdown is requested, lets the
  currently accepted handler finish, then closes the listen socket and returns
  `SS_HTTP_OK`.
- Buffered requests are capped at 1 MiB by the fallback adapter to prevent
  unbounded allocation. Apps enforce smaller API body policies through
  `http.requestBodyLength` and return their own envelopes.
- Long-lived response streaming is still not supported by this adapter. Every
  response path is one-shot, emits `Content-Length`, and closes the connection;
  `ss_http_response_sse_event` formats a single SSE frame body rather than
  holding an event stream open.
- `SEM_HTTP_WITH_H2O=ON` is reserved for the next step: replacing the fallback
  backend with `libh2o-evloop` / H2O.

Local compile smoke:

```powershell
cmake -S SemanticScript/runtime/native_http -B SemanticScript/runtime/native_http/build -G Ninja
cmake --build SemanticScript/runtime/native_http/build
```

On the current Windows toolchain, pass clang and LLVM's resource compiler
explicitly:

```powershell
cmake -S SemanticScript/runtime/native_http -B SemanticScript/runtime/native_http/build -G Ninja `
  -DCMAKE_C_COMPILER="C:/Program Files/LLVM/bin/clang.exe" `
  -DCMAKE_RC_COMPILER="C:/Program Files/LLVM/bin/llvm-rc.exe"
```

The CMake demo executable starts a blocking server. The curated app set keeps
repeatable end-to-end HTTP tests:

```powershell
python apps/http-runtime-gauntlet/scripts/test_http_runtime_gauntlet.py
python apps/taskforge-web/scripts/test_taskforge_web.py
```
