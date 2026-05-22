# TaskForge API Client

Standalone todo client for the `taskforge-web` JSON API. It serves a browser UI and proxies relative `/api/*` requests to the TaskForge backend so session cookies work without browser CORS setup.

The client is intentionally a separate app from `taskforge-web`. Browser code calls `/api/...` on the client origin, and `scripts/dev_proxy.py` forwards those requests to the real TaskForge API at `http://127.0.0.1:18090`. Upstream `Set-Cookie` headers are copied back to the browser, then later browser requests send the same session cookie back through the proxy.

## Run

Start the existing TaskForge API first:

```powershell
python -m SemanticScript.compiler.semsc apps/taskforge-web/build.sem --emit-exe --quiet
.\apps\taskforge-web\build\taskforge_web.exe
```

Then start the client:

```powershell
python apps/taskforge-api-client/scripts/dev_proxy.py
```

Open `http://127.0.0.1:18120`. The seeded demo account is `demo` / `demo1234`.

To point the client at a different TaskForge API origin:

```powershell
python apps/taskforge-api-client/scripts/dev_proxy.py --api-origin http://127.0.0.1:18090 --port 18120
```

## Source Layout

```text
apps/taskforge-api-client/
  index.html                  browser shell
  styles.css                  responsive todo workspace styling
  app.js                      login, fetch, create, toggle, delete, search, filters
  scripts/dev_proxy.py        static-file server + /api/* proxy
  scripts/test_taskforge_api_client.py
```

## Behavior

- Signs in through `POST /api/auth/login` and stores the TaskForge session cookie on the client origin.
- Fetches the current session user through `GET /api/auth/me`.
- Fetches todos through `GET /api/todos`.
- Creates todos through `POST /api/todos`.
- Toggles completion through `POST /api/todos/:id/complete` and `POST /api/todos/:id/uncomplete`.
- Deletes todos through `DELETE /api/todos/:id`.
- Filters and searches the fetched list in-browser without changing the API contract.

## API Surface Used

- `GET /api/version`
- `POST /api/auth/login`
- `GET /api/auth/me`
- `POST /api/auth/logout`
- `GET /api/todos`
- `POST /api/todos`
- `POST /api/todos/:id/complete`
- `POST /api/todos/:id/uncomplete`
- `DELETE /api/todos/:id`

## Test

```powershell
python apps/taskforge-api-client/scripts/test_taskforge_api_client.py
```

The test starts a fake TaskForge API and the proxy, then verifies auth cookies, todo fetch, create, complete, and delete through the same relative API paths the browser app uses.
