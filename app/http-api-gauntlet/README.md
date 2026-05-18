# HTTP API Gauntlet

Complex native HTTP demo for SemanticScript. It exercises the current HTTP API
surface harder than the todo web sample:

- exact method/path dispatch across `GET`, `POST`, `PUT`, `PATCH`, `DELETE`,
  and `OPTIONS`;
- request method, path, header, query, body text, and body length reads;
- raw request body byte reads and response byte writes with explicit length;
- bounded multipart text and file part reads, including filename and content
  type metadata;
- one-shot SSE event response formatting;
- response body, response status, custom content type, and response headers;
- path-scoped middleware that reads the request path and adds response headers;
- 204, 302, 400, 404, 413, and 500 runtime paths;
- repeated sequential requests against one native server process.

`/reflect/required-header-or-fail` is intentionally a negative-test route: it
returns `500 handler failed` when `X-Gauntlet-Required` is absent. Likewise,
`/reflect/header` returns the current null-body failure path when
`X-Gauntlet-Token` is absent.

Known intentional gaps are still visible: no path parameters, no route timeout
enforcement, no structured JSON/form body decoder, no static file helper, no
graceful shutdown hook, no long-lived streaming response API, and no HTTP/2
backend.

## Check

```powershell
cd C:\Users\Cam\Desktop\AgentScript
python app\http-api-gauntlet\test_http_api_gauntlet.py
.\app\http-api-gauntlet\check_http_api_gauntlet.ps1
```
