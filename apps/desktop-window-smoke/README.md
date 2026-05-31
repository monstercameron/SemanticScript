# desktop-window-smoke (EAV port)

Full 1:1 EAV-Steps port of `apps/desktop-window-smoke` (the v0.1 SemanticScript
Windows GUI smoke app).

## Parity

- **4 operations** — `main`, `appendGreetingFromInput`, `inspectSelectedGreeting`,
  `clearGreetings` — matching the original op count exactly.
- **19 module-storage** entities, matching the original.
- **31 call entities** — the original's inline `call`/`argument`/`run` records,
  promoted to first-class `call` entities (the §20 call/task/cleanup split).
- Every `gui.*` call from the original is converted against
  `sigs/standard.gui.semsig` (16 intrinsics).

## Conversions

- The original's inline `authority ACTION RESOURCE` rows become covering
  `capability`/`grants` + `uses` pairs (EAV's effect model, §8): one authority
  capability for the composition op and one per event handler.
- `set storage HANDLE VALUE` becomes a create call whose `out` rebinds the
  mutable module-storage handle (`createTaskInputCall out greetingInputHandle …`),
  with a `write storage.<handle>` effect on `main` (README §12).
- `bind value`/`ignore value source … type Int32` become `out NAME TYPE` /
  `discards "reason"` on the call entity.

## Deferred execution

GUI execution is deferred: `target windowsGui` is reserved and hard-errors
(SS0744, §27). The original's `entry console main` is preserved, so the port
declares `target console` and the `gui.*` targets stay external (unlowered).
The whole app parses + lints clean. When a GUI runtime module is specified, the
`gui.*` intrinsics gain bodies and this source runs unchanged — no source
changes required.
