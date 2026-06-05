# taskforge-api-client (SemanticScript port)

Full 1:1 SemanticScript port of `apps/taskforge-api-client` (the v0.1 SemanticScript
async outbound HTTP client that probes a running `apps/taskforge-web` server).

## Parity

- **1 operation** — `main` — matching the original.
- **3 capabilities** (outboundFetch / consoleStdoutWriteCapability /
  fetchBodyHeapRelease), matching the original.
- **3 fetch tasks + 17 calls** — the original's inline async `call`/`start`
  records and `new`/`fieldSet` builders, promoted to first-class `task`/`call`
  entities (the §20 split). Every `net.fetchText` / `net.freeTextBody` call is
  converted against `sigs/standard.net.semsig` (the high-level client surface).
- The async shape is preserved: all three fetches are **started before** the
  first response is joined (asserted by the test).

## Conversions / language differences

- The original's `new HttpGetRequest` + `fieldSet` mutable builder becomes
  immutable `HttpRequestPolicy.new` / `HttpGetRequest.new` construction, and
  `fieldGet … body` becomes `HttpTextResponse.body` field access.
- The wait-set `await … case … done` (await-any in completion order) becomes
  start-all-then-join-each in document order — SemanticScript has no select/wait-set, so
  the dynamic dispatch becomes a deterministic join order.
- Dropped (language differences, not feature reductions): per-call
  `timeout`/`cancelOn` (SemanticScript tasks carry no cancel token; `requestCancellationToken`
  storage drops, 12→11), the `Result ExitCode MainError` return + `makeError`
  (a console entry returns `ExitCode`), and the `console.writeLine` error path
  (console.writeLine is void in SemanticScript).

## Runtime behavior

`net.fetchText` now lowers through the native `ss_net` HTTP client and
`net.freeTextBody` releases the heap-owned body returned by that client. The
current runtime is HTTP-only: `http://` URLs run, while `https://` URLs reject at
check time until a TLS backend is added. The whole app parses, lints, and runs as
`target console` against the local TaskForge server.
