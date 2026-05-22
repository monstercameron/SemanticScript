# TaskForge API Client

SemanticScript outbound HTTP client demo for the `taskforge-web` server. The primary app is `main.sem`: it starts multiple `standard.net` fetches against `http://127.0.0.1:18090`, does local console work, then awaits and prints the responses.

The client is intentionally a separate app from `taskforge-web`; it exists to explore async source shape, not to reimplement the server.

## Run

Start the existing TaskForge API first:

```powershell
python -m SemanticScript.compiler.semsc apps/taskforge-web/build.sem --emit-exe --quiet
.\apps\taskforge-web\build\taskforge_web.exe
```

Then inspect or compile the SemanticScript client:

```powershell
python -m SemanticScript.compiler.semsc apps/taskforge-api-client/build.sem --lint --parse-only
python SemanticScript/compiler/semsc.py apps/taskforge-api-client/main.sem --emit-ir --quiet
```

To build and run the same SemanticScript client with the real libuv/libcurl runtime:

```powershell
python apps/taskforge-api-client/scripts/build_async_client.py --run
```

That script emits LLVM IR from `main.sem`, builds the native HTTP client runtime with `SEM_ASYNC_WITH_LIBUV=ON` and `SEM_HTTP_CLIENT_WITH_CURL=ON`, links the generated client, checks that `taskforge-web` is reachable, and runs the executable.

`main.sem` starts these fetches before awaiting any response:

- `GET http://127.0.0.1:18090/health`
- `GET http://127.0.0.1:18090/api/version`
- `GET http://127.0.0.1:18090/api/todos`

`/api/todos` is intentionally unauthenticated in this source demo. The current `standard.net` prototype supports GET request records but does not yet expose POST login, request bodies, custom Cookie headers, or response Set-Cookie capture. Until those land, this client demonstrates the async call pattern and prints TaskForge's `401` JSON for the protected route.

## Source Layout

```text
apps/taskforge-api-client/
  build.sem                   SemanticScript build plan
  main.sem                    async standard.net TaskForge API client
  index.html                  optional browser shell
  styles.css                  optional browser styling
  app.js                      optional browser todo workflow
  scripts/build_async_client.py
                              real libuv/libcurl build for main.sem
  scripts/test_taskforge_async_client.py
                              source checks plus optional real-backend run
  scripts/dev_proxy.py        optional static-file server + /api/* proxy
  scripts/test_taskforge_api_client.py
```

## Optional Browser Harness

The browser harness is not the async-code demo. It exists only to exercise the full authenticated TaskForge todo API today, using a Python same-origin proxy to preserve auth cookies while `standard.net` is still GET-only.

```powershell
python apps/taskforge-api-client/scripts/dev_proxy.py
```

Open `http://127.0.0.1:18120`. The seeded demo account is `demo` / `demo1234`.

To point the client at a different TaskForge API origin:

```powershell
python apps/taskforge-api-client/scripts/dev_proxy.py --api-origin http://127.0.0.1:18090 --port 18120
```

## Browser Harness Behavior

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
python apps/taskforge-api-client/scripts/test_taskforge_async_client.py
python apps/taskforge-api-client/scripts/test_taskforge_async_client.py --real-backend
```

`test_taskforge_api_client.py` starts a fake TaskForge API and the optional browser proxy, then verifies auth cookies, todo fetch, create, complete, and delete through the same relative API paths the browser app uses.

`test_taskforge_async_client.py` checks the SemanticScript app shape. With `--real-backend`, it also builds the generated client against real libuv/libcurl and verifies the response bodies from the running TaskForge server.
