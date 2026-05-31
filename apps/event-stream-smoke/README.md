# event-stream-smoke (SemanticScript port)

Full 1:1 SemanticScript port of `apps/event-stream-smoke` (the v0.1 SemanticScript
`standard.event` one-emitter-to-many-listeners smoke app).

## Parity

- **4 operations** — `eventIdGreaterThan`, `listenerOneHandleSmokeEvent`,
  `listenerTwoHandleSmokeEvent`, `main` — matching the original op count exactly.
- **12 capabilities**, matching the original (the original's resource-first
  `capability NAME RESOURCE ACTION` rows become SemanticScript `capability` entities with
  `grants ACTION RESOURCE` + `uses`, §8).
- **17 task entities + 3 call entities** — the original's inline async
  `call`/`start`/`await` records, promoted to first-class `task`/`call` entities
  (the §20 split). Every `event.*` call is a `task` (SemanticScript async = `start`/`join`,
  §13), converted against `sigs/standard.event.semsig` (7 intrinsics).

## Conversions / language differences

- `storage`: 13 → 12. The only dropped storage is `requestCancellationToken`,
  used solely by the v0.1 `cancelOn` rows; SemanticScript tasks carry no per-task cancel
  token, so `timeout`/`cancelOn` are not represented (a language difference, not
  a feature reduction).
- The v0.1 `console.writeLine` error path in each listener is dropped:
  `console.writeLine` is infallible (void) in SemanticScript, so the `bind error` /
  `writeFailed` label disappears.
- `start CALL` / `await CALL` / `bind value X T CALL` → an SemanticScript `task` with
  `out X T`, resolved by `start` + `join`.

## Deferred execution

The event stream/subscription runtime is not specified in v0.3 (§27), so the
`event.*` targets stay external (unlowered) and the listeners never receive a
real event. The whole app parses + lints clean as `target console`. When the
event runtime lands, the `event.*` intrinsics gain bodies and this source runs
unchanged — no source changes required.
