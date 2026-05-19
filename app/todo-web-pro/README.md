# Todo Web Pro

Production-grade multi-user todo web app for SemanticScript. The runtime
foundation is complete (bcrypt password hashing, sqlite persistence, JSON
encode/decode, HTTP with path-params + cookies + file serving + session
cookies); the handler bodies for register, login, DB persistence, and
cookie issue are wired through end-to-end. Session validation and the rest
of the CRUD surface are scaffold-ready and ship in the next iteration.

## What works today (v1.0)

- `GET /health` — JSON liveness body
- `GET /api/version` — name + version + bcrypt cost factor
- `POST /api/auth/register` — full implementation: validates JSON body,
  bcrypt-cost-12 hashes the password, INSERTs the user, mints a 32-byte
  base64url session token, INSERTs the session row, returns `201` with
  the user record JSON and a `Set-Cookie: session=<token>; HttpOnly;
  SameSite=Strict; Max-Age=2592000; Path=/` header.
- `POST /api/auth/login` — verifies the submitted password with
  `bcrypt.verifyPassword`, mints a fresh session token on success, returns
  `200` with the user record JSON and the same HttpOnly session cookie
  shape used by register. Bad usernames, bad passwords, and malformed
  bodies all return the same `401` JSON response shape.
- Schema bootstrap: `users + sessions + todos + todo_images` tables
  with CHECK / NOT NULL / FOREIGN KEY constraints, applied at startup
  via a single `sqlite.exec` of the literal-loaded `schema.sql`.
  The schema also seeds a `demo` user (`demo1234`) and sample todos for
  first-run manual testing.

## Scaffolded but not yet validated (v1.1 follow-up)

- `POST /api/auth/logout` — wired (writes clear-cookie + 200), but
  session validation chain (`requireSessionUserId`) needs debugging
  before it can reliably DELETE the right session row.
- `GET /api/auth/me` — wired (returns 401 without session, would
  return user record with session), but the session lookup currently
  fails to find the row even when the cookie matches the DB token.
  Bug investigation deferred — DB rows verified correct, cookie
  value verified correct, but `requireSessionUserId` returns -1.
- `GET /api/todos` — same situation (returns 401 without session).
- `POST /api/todos` — same.
- `GET /api/todos/:id`, `DELETE /api/todos/:id`,
  `POST /api/todos/:id/complete` — 501 stubs.
- Image upload + serve — runtime support is in place
  (`http.responseFile`, multipart parsing, 8 MiB body cap) but the
  app handlers are not yet wired.
- HTML pages via `standard.html` — module imported but no
  page templates yet.

## Architecture

```
app/todo-web-pro/
  build.sem                       # project tape, target webServer, VERSIONINFO
  main.sem                        # webServer + 11 routes + 14 operations
  schema.sql                      # vendored as literal source at compile time
  scripts/
    test_todo_web_pro.py          # end-to-end harness
  build/                          # gitignored: exe + db + ll + resources
```

## Runtime stack

The app links four native runtime adapters:

- `standard.http` (`SemanticScript/runtime/native_http/`) — request
  dispatch, path-param matcher, cookies, multipart, response file
  serving, millisecond clock, mkdir.
- `standard.sqlite` (`SemanticScript/runtime/native_sqlite/`) — the
  vendored SQLite 3.53.1 amalgamation (`third_party/sqlite/`).
- `standard.json` (`SemanticScript/runtime/native_json/`) — opaque
  builder + finder API with RFC 8259 escape handling.
- `standard.bcrypt` (`SemanticScript/runtime/native_bcrypt/`) — the
  vendored crypt_blowfish 1.3 (`third_party/bcrypt/`) + platform
  CSPRNG + base64url encoder.

All four are pulled in automatically by the linker when the program
references the matching `<runtime>.*` call targets.

## Build + run

```powershell
cd C:\Users\Cam\Desktop\AgentScript
python -m SemanticScript.compiler.semsc app/todo-web-pro/build.sem --lint --parse-only
python -m SemanticScript.compiler.semsc app/todo-web-pro/build.sem --emit-exe --quiet
.\app\todo-web-pro\build\todo_web_pro.exe
```

The server listens on `http://127.0.0.1:18090` and creates `todo_web_pro.db`
in the current working directory plus an `images/` subdirectory for future
file-backed image uploads.

```powershell
# Manual smoke against a running server:
curl http://127.0.0.1:18090/health
curl http://127.0.0.1:18090/api/version
curl -X POST http://127.0.0.1:18090/api/auth/register `
  -H "Content-Type: application/json" `
  -d '{"username":"alice","password":"secret123"}'
curl -X POST http://127.0.0.1:18090/api/auth/login `
  -H "Content-Type: application/json" `
  -d '{"username":"demo","password":"demo1234"}'
```

The register POST should return `201` with a JSON body like
`{"user":{"id":1,"username":"alice","displayName":""}}` and a
`Set-Cookie: session=<43-char-base64url>; …` response header. The
session row will appear in the `sessions` table of `todo_web_pro.db`.

## Test harness

```powershell
python app/todo-web-pro/scripts/test_todo_web_pro.py
```

Lints, builds, starts, polls `/health`, exercises every shipped route
plus the registration and login flows, asserts the resulting DB rows
match the returned cookies, then tears the server down. Exit 0 on
success, non-zero on first failed assertion.

## Compiler bug fixed in this session

`semsc.py`'s default `branchIfError` for user-op calls that return a
pointer (Result<Pointer, _>) was inverted: the error condition was set
to `result != null`, which meant successful calls (returning real
handles) were treated as failures and vice versa. The fix flips it to
`result == null` (NULL pointer is the failure marker, per the comment
in the code). The bug is documented at SemanticScript/compiler/semsc.py
in the user-op call lowering block — see the comment block in front of
the icmp_unsigned line.

## What's intentionally not in v1

- `routeMiddleware` for structured request logging (planned for v1.2)
- HTML pages via `standard.html` (the standard module is imported but
  no templates yet)
- Tailwind CSS asset serving via `http.responseFile`
- CSRF synchronizer tokens (we rely on `SameSite=Strict` only per the
  plan)
- Image upload + serve (runtime support exists; app handlers don't)
- Stats endpoint
- OpenAPI / Swagger generation
