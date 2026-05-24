# HTTP Runtime Gauntlet

Native HTTP conformance harness for SemanticScript. This is not a product demo; it is the broad regression target for the HTTP runtime and compiler lowering.

## Coverage

- Exact method/path dispatch for `GET`, `POST`, `PUT`, `PATCH`, `DELETE`, and `OPTIONS`.
- Request method, path, header, query, body text, body length, and raw body reads.
- Response text, bytes, status, content type, custom headers, redirects, and empty-body status codes.
- Multipart text and file reads, including filename and content type metadata.
- One-shot SSE event formatting.
- Path-scoped middleware that reads the request and mutates the response.
- Negative runtime paths for 400, 404, 413, and handler failure behavior.
- Repeated sequential requests against one native server process.

Known intentional gaps remain visible: route timeout enforcement, structured JSON/form decoding, static file helpers, graceful shutdown hooks, long-lived streaming, and HTTP/2.

## Check

```powershell
cd C:\Users\Cam\Desktop\AgentScript
python apps\http-runtime-gauntlet\scripts\test_http_runtime_gauntlet.py
.\apps\http-runtime-gauntlet\scripts\check_http_runtime_gauntlet.ps1
```

Use this app when changing native HTTP, request/response intrinsics, middleware control, or webServer lowering.
