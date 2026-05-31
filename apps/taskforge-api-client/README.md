# taskforge-api-client (EAV port)

Full 1:1 EAV-Steps port of `apps/taskforge-api-client` (the v0.1 SemanticScript
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
  start-all-then-join-each in document order — EAV has no select/wait-set, so
  the dynamic dispatch becomes a deterministic join order.
- Dropped (language differences, not feature reductions): per-call
  `timeout`/`cancelOn` (EAV tasks carry no cancel token; `requestCancellationToken`
  storage drops, 12→11), the `Result ExitCode MainError` return + `makeError`
  (a console entry returns `ExitCode`), and the `console.writeLine` error path
  (console.writeLine is void in EAV).

## Deferred execution

The `standard.net` client runtime is not specified in v0.3 (§27), so the `net.*`
targets stay external (unlowered). The record construction/access ops are real
EAV record lowering, but the program cannot run until the net runtime lands.
The whole app parses + lints clean as `target console`; when `net.fetchText` /
`net.freeTextBody` gain bodies, this source runs unchanged — no source changes.
