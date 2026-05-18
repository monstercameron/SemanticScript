# Advanced Todo Web Demo

SemanticScript webserver demo that pushes the current native HTTP API edges.

## What It Exercises

- Multiple exact routes in one `webServer`.
- Method-specific dispatch for `GET`, `POST`, `PUT`, `DELETE`, and `OPTIONS`.
- Query-string stripping before route matching.
- `http.requestMethod`, `http.requestPath`, `http.requestHeader`,
  `http.requestQueryParam`, and `http.requestBodyText` runtime reads.
- `http.responseHeader` for custom response headers.
- Path-scoped `routeMiddleware` execution before the route handler.
- Shared response helper operation that writes through `HttpResponse`.
- Repeated sequential requests against one server process.
- Bounded request-body buffering for POST and PUT bodies.
- Malformed raw HTTP request handling.
- Case-insensitive method matching.
- Real native executable build through `semsc.py --emit-exe`.
- Real HTTP requests through Python's `http.client`.

## Known Missing API Pieces

The demo intentionally exposes the next gaps:

- No path-parameter matcher yet, so `/todos/1` is explicit instead of
  `/todos/:todoId`.
- No percent-decoding or repeated-key model for query parameters yet.
- No request body JSON/form decoder or persistent storage yet, so create/update
  handlers return placeholders.
- No JSON response helper yet.
- No method-scoped middleware selection yet; current middleware is path-scoped.
- No route timeout enforcement yet; `routeTimeout` is still metadata and tests
  avoid implying a timeout guarantee.
- No static-file serving helper yet.
- No graceful shutdown hook yet.

## Check

```powershell
cd C:\Users\Cam\Desktop\AgentScript
python app\todo-web-advanced\test_advanced_todo_web.py
```

The test compiles the app, starts the native webserver on
`127.0.0.1:18081`, performs edge-case HTTP requests, and stops the process.
