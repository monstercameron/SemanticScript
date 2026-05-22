# Native HTTP Runtime Adapter

This adapter is the SemanticScript-owned boundary between generated route
handlers and the selected native HTTP engine. The first engine target is
`third_party/h2o`.

Current status:

- The public C ABI compiles as a standalone static library.
- The default backend is a small blocking HTTP/1.1 socket server for exact-route
  development and tests.
- The default backend now supports request method/path/header/query/body-text
  and body-byte reads, bounded multipart part reads, response text/bytes,
  one-shot SSE event bodies, response header writes, and one path-scoped
  middleware callback.
- Request bodies are bounded to 64 KiB of headers plus body. Larger requests
  return `413 Payload Too Large`.
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
