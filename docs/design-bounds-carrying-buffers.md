# Design: bounds-carrying buffers (the fat-pointer foundation)

Status: proposed. Owner: unassigned. Unblocks: R-130, R-188, R-202, R-203, R-205.

## Why this exists

Five open memory-safety findings reduce to one missing capability. Each one
trusts a *bare* address (and sometimes a separately-supplied length) with no
proof that the address points into a live allocation of at least that size:

| Finding | Surface | What it trusts today |
| --- | --- | --- |
| R-130 | `pointer.offset` / `pointer.loadByte` / `pointer.storeByte` | a raw `OpaquePointer` + caller-computed byte offset |
| R-188 | the same three ops, but reachable from **app** code | same |
| R-202 | `standard.bcrypt` buffer intrinsics | a raw `OpaquePointer` + caller count |
| R-203 | `standard.json` scratch APIs (`cursorString`, `serializeDocument`) | a raw `OpaquePointer` capacity |
| R-205 | `http.responseBytes` | a raw body pointer + a caller-supplied length |

A side registry that only records *which* allocations are live cannot fix
these. Proven during the R-188 investigation: for a 1-byte `loadByte(addr)`,
an in-range `addr` is trivially inside the tracked range and a past-the-end
`addr` is inside *no* tracked range — so it reads as "untracked" and is
allowed. The registry can answer "is this a known base pointer?" but not "is
`base+off .. base+off+n` within the allocation `base` came from?", because the
derived address has lost its origin. The bound must travel **with** the
pointer. That is a fat pointer.

## The representation

Introduce one runtime value type, exposed to the language as the existing
`Buffer` handle, lowered as a 3-word struct (not a bare `i64`):

```
struct SsBuffer {     // 24 bytes on a 64-bit host
    uint8_t *base;    // start of the live allocation (or NULL once released)
    size_t   len;     // usable byte length [0, len)
    uint64_t epoch;   // bumped on release; pairs with the live-registry slot
};
```

`base` + `len` give spatial safety; `epoch` (checked against the per-buffer
live-registry slot, the existing tombstone pattern — see
`ss-runtime-tombstone-pattern`) gives temporal safety against use-after-free.
Every access is `assert(base != NULL && epoch == live[base].epoch && off + n <= len)`
before the load/store; failure raises a runtime panic (new `SSR00xx`) rather
than reading wild memory.

This is deliberately the *same* `Buffer` the bounds-checked `buffer.get` /
`buffer.set` / `buffer.length` / `buffer.release` ops already use (R-206/R-207
gave it the tombstone + release contract). We are not adding a second memory
abstraction; we are making the existing one carry its bound across the FFI
boundary and across pointer derivation.

## Lowering changes (semanticscript.py)

1. `OpaquePointer` stays an `i64` for genuine opaque FFI handles (sockets,
   `FILE*`, sqlite handles) — those are never indexed, so they need no bound.
2. A new `Slice` (or reuse `Buffer`) lowers to the `SsBuffer` struct above.
3. `pointer.offset(buf, n)` → a *checked* slice narrowing: returns a `Buffer`
   with `base += n`, `len -= n`, same `epoch`; panics if `n > len`. It no
   longer accepts a bare `OpaquePointer`.
4. `pointer.loadByte` / `pointer.storeByte` take a `Buffer` + index, bounds-
   checked against `len`. (This is exactly `buffer.get` / `buffer.set`; the
   `pointer.*` spellings become thin aliases, then deprecate.)
5. App-tier lint (closes R-188): `pointer.offset/loadByte/storeByte` against a
   bare `OpaquePointer` become a deny-tier diagnostic outside stdlib-internal
   `unsafe`-marked ops; the steering fix is "take a `Buffer`."

## FFI boundary (coordinate with `ss_runtime_export.h`)

The C runtime functions that today take `(void *ptr, size_t n)` change to take
an `SsBuffer` by value (or `const SsBuffer *`). Concretely:

- `ss_http_response_bytes(... body, len)` → `ss_http_response_bytes(... SsBuffer body)`.
  The length now comes from the buffer, so R-205's mismatch is unrepresentable.
- `ss_bcrypt_*` buffer intrinsics → take `SsBuffer`; R-202 closed.
- `ss_json` scratch APIs → take `SsBuffer`; R-203 closed.

The request body that HTTP hands to app code must itself become an `SsBuffer`
(`request.body` view = `{base = parsed_body, len = body_length, epoch = request_epoch}`),
so echoing the body to `responseBytes` is bound-preserving end to end.

## Migration order (each step independently shippable + green)

1. Land `SsBuffer` struct + the live/epoch registry in the runtime; keep the
   old `(ptr, len)` C entry points as thin wrappers that synthesize an
   `SsBuffer` (no caller changes yet). **Validates: full suite still green.**
2. Lower `Buffer` to `SsBuffer`; route `buffer.get/set/length/release` through
   the checked accessors. **Validates: `buffer_roundtrip` + `test_apps`.**
3. Convert `pointer.offset/loadByte/storeByte` to `Buffer`-checked aliases.
   **Validates: any pointer-using example.**
4. Migrate `taskforge-tui`'s c.malloc + raw-pointer buffer layer onto
   `Buffer`. **Validates: `test_apps` taskforge-tui markers.** Closes R-130/R-188.
5. Flip the FFI signatures (`responseBytes`, bcrypt, json) to `SsBuffer`,
   migrate the apps that call them. **Validates: port-parity + `test_apps`.**
   Closes R-202/R-203/R-205.
6. Add the app-tier deny-lint for bare-pointer arithmetic + the `unsafe`
   stdlib-internal escape hatch. **Validates: a neg fixture per finding.**

Steps 1–3 are foundation; 4–6 close the findings. Each step is gated by an
existing harness, so a regression surfaces at that step rather than at the end.

## Why not just cap/clamp (the current R-205 mitigation)

The 64 MiB cap on `responseBytes` (commit 9008610) bounds the *blast radius*
of an OOB read but does not prevent it — a 1 KiB over-read is still wild
memory. The cap stays as defense-in-depth; this design is the actual fix.
