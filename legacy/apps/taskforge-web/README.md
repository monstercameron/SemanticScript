# TaskForge Web

Multi-user todo web app for SemanticScript. This preview demo exercises native
HTTP, HTML templates, static JavaScript assets, bcrypt password hashing, sqlite
persistence, JSON APIs, sessions, and cookie flow.

## What Works

- `GET /`: HTML shell assembled from SemanticScript template modules.
- `GET /assets/home.js` and `GET /assets/dashboard.js`: static JavaScript assets.
- `GET /health`: JSON liveness body.
- `GET /api/version`: app name, version, and bcrypt cost.
- `POST /api/auth/register`: validates JSON, hashes the password, inserts the user, creates a session, and returns a `Set-Cookie` header.
- `POST /api/auth/login`: verifies credentials, creates a fresh session, and rejects bad credentials with the same safe response shape.
- `GET /api/auth/me`: returns the current session user.
- `POST /api/auth/logout`: clears the session row and cookie.
- `GET /api/todos`: lists todos for the current session user.
- `POST /api/todos`: inserts a todo for the current session user.
- `POST /api/todos/:id/complete`: marks a todo done for the current session user.
- `POST /api/todos/:id/uncomplete`: reopens a completed todo for the current session user.
- `DELETE /api/todos/:id`: deletes a todo owned by the current session user.
- Unknown routes return 404.

Known preview gap: `GET /api/todos/:id` currently returns 501 until the show
route has full record serialization. Use the collection route and mutation
routes as the maintained web-demo surface.

## Source Layout

```text
apps/taskforge-web/
  build.sem
  main.sem
  components/main.sem
  pages/main.sem
  assets/
  sql/
  scripts/test_taskforge_web.py
```

`build.sem` supplies the typed BuildPlan and build constants. `main.sem` owns server routes, auth/session flow, sqlite calls, and JSON handlers. `components/` and `pages/` own reusable HTML fragments.

## Build And Run

From the repository root:

```powershell
python -m SemanticScript.compiler.semsc apps/taskforge-web/build.sem --lint --parse-only
python -m SemanticScript.compiler.semsc apps/taskforge-web/build.sem --emit-exe --quiet
.\apps\taskforge-web\build\taskforge-web.exe
```

The server listens on `http://127.0.0.1:18090`. Native webServer entrypoints
switch the process working directory to the executable directory at startup, so
`taskforge_web.db`, logs, copied assets, and future image uploads resolve under
`build/` even when the exe is launched from another directory.

## Test Harness

```powershell
python apps/taskforge-web/scripts/test_taskforge_web.py
```

The harness lints, builds, starts the server, polls `/health`, exercises the
HTML shell, assets, auth flows, session routes, todo list/create routes, and
the documented preview gap, then tears the server down.
