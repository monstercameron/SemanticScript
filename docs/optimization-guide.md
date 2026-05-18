# SemanticScript Optimization Guide

This guide collects optimization rules that preserve SemanticScript's main value: visible dataflow and explicit failure contracts. Performance work should not erase semantic context.

## Return Contracts

Do not let raw C return values escape an operation unless the operation's contract explicitly says that raw value is the result.

Many libc calls return useful counts on success:

```semanticscript
c.printf    # positive byte count on success, negative on failure
c.fprintf   # positive byte count on success, negative on failure
c.fread     # item count
c.fwrite    # item count
```

Those values are not canonical SemanticScript operation status codes. If an operation only needs to report success or failure, normalize the return:

```semanticscript
enum SaveStatus repr CSignedInt32
enumCase SaveStatus SaveSucceeded 0
enumCase SaveStatus SaveFailed 1

call writeJsonCall c.fprintf
arg writeJsonCall stream saveFileHandle
arg writeJsonCall format saveFormat
run writeJsonCall
ignoreValue writeJsonCall CSignedInt32
returnValue SaveSucceeded
```

Avoid this shape:

```semanticscript
bind writeJsonResult CSignedInt32 writeJsonCall
returnValue writeJsonResult
```

That leaks a libc byte count into the operation boundary. A caller or backend may later interpret a nonzero scalar as failure-like control flow.

## Linter Guardrail

`semlint2.py` (the canonical linter — `semlint.py` is legacy) reports
structured diagnostics under stable SS codes; the guardrails below cite the
codes that enforce each rule so agents can grep both this guide and the
linter's `kind` strings against the same vocabulary.

`semlint.py` reports `rawLibcReturnEscapesOperation` when an operation returns a binding produced by libc count/status calls such as `c.printf`, `c.fprintf`, `c.fread`, or `c.fwrite`.

The intended fix is one of:

- Map the raw value to an explicit domain status.
- Use `Result OkType ErrorType` and branch on the C call's real failure condition.
- Rename/retype the operation so the raw byte/count value is honestly the public result.

Do not declare `Result SomeValue Void` for helpers that cannot actually
`returnError`. That shape makes callers use fallible syntax for an infallible
operation and can interact badly with the current user-operation ABI, where the
success payload is the concrete return slot. Use a plain output instead:

```semanticscript
output copyStringBuffer CSignedInt64
```

`semlint.py` reports `resultVoidErrorWithoutFailurePath` when an operation
declares `Result A Void` without any `returnError` path.

## App Boundary Rule

Treat `c.*` as a bootstrap/backend boundary, not as the normal application API.
Application code should call SemanticScript-facing operations once a matching
surface exists:

```text
console.readKey
console.readLineIntoBuffer
console.writeText
console.writeLine
console.clearScreen
file.openRead
file.openWrite
file.close
file.readLineIntoBuffer
file.writeText
file.writeBytes
memory.allocate
memory.free
memory.zero
memory.copy
```

Direct `c.*` calls are acceptable in low-level bootstrap/runtime modules,
stdlib implementation files, compiler smoke tests, and backend bring-up samples.
They should be avoided in top-level apps and user-facing examples unless the
top-level SemanticScript API is still missing.

This keeps the dependency direction clean: apps depend on SemanticScript
contracts, stdlib/runtime code owns the temporary C bootstrap, and the backend
can later replace libc with Win32, POSIX syscalls, or a custom runtime without
rewriting app code.

## Effect And Capability Precision

Effects should describe behavior an operation actually performs, not everything
the surrounding route or runtime could provide. A static HTTP handler that only
writes a response should declare:

```semanticscript
effect healthHandler write http.response
```

Do not keep request-read effects on static handlers just because the handler has
an `HttpRequest` input. Declare request effects when the body calls a matching
runtime reader:

```semanticscript
call methodReadCall http.requestMethod
effect methodEchoHandler read http.request.method
```

Helper operations need their own capability proof. Caller authority does not
automatically cover a callee's declared effect, so response helpers should be
self-contained:

```semanticscript
capability httpResponseWriter http.response write

operation writeTextResponse
effect writeTextResponse write http.response
useCapability writeTextResponse httpResponseWriter
```

Capability paths are hierarchical. A broad capability such as:

```semanticscript
capability httpRequestReader http.request read
```

authorizes narrower effects such as `read http.request.method` and
`read http.request.path`. Prefer narrower capabilities when the distinction is
security-relevant, but do not leave the relationship fuzzy in app code or docs.

## Filesystem Authority Precision

File effects should match the mode and calls in the operation body. A loader
that opens with `"r"` should not declare `write filesystem`, and a saver that
opens with `"w"` should not declare `read filesystem` unless it also performs a
real read.

Prefer this shape:

```semanticscript
operation loadTodosFromJson
effect loadTodosFromJson read filesystem
effect loadTodosFromJson open file
effect loadTodosFromJson close file
```

```semanticscript
operation saveTodosToJson
effect saveTodosToJson write filesystem
effect saveTodosToJson open file
effect saveTodosToJson close file
```

Avoid carrying both filesystem read and write on every file helper. It makes the
authority model less useful and hides accidental direction changes during later
patches.

`semlint.py` reports `overAuthorizedEffect` when a `read filesystem` or
`write filesystem` declaration is not justified by the file mode, direct file
I/O call, or local operation call in the body. The compiler lint also treats
`c.fopen`/`c.freopen` mode strings as the source of read/write filesystem
requirements, and both compiler lint and `semlint.py` require `open file` /
`close file` for direct open/close calls.

## Route Metadata Selectors

Route metadata should point at a route selector that exists in the source. Until
named route syntax exists, selectors are route paths. For app-wide behavior,
repeat the metadata for each route path instead of inventing a wildcard the
runtime does not understand yet:

```semanticscript
route advancedTodoWebServer GET "/" homeHandler
routeTimeout advancedTodoWebServer "/" requestTimeoutBudget
routeMiddleware advancedTodoWebServer "/" requestLogMiddleware

route advancedTodoWebServer GET "/todos" listTodosHandler
route advancedTodoWebServer POST "/todos" createTodoHandler
routeTimeout advancedTodoWebServer "/todos" requestTimeoutBudget
routeMiddleware advancedTodoWebServer "/todos" requestLogMiddleware
```

Avoid invented route IDs such as `homeRoute` unless the route row itself binds
that name. Dangling route metadata is hard for agents to repair because it is
unclear whether the route, the path, or the metadata row is authoritative.

## Serialization Boundaries

Do not optimize JSON or other structured output by splicing untrusted or
user-editable strings directly into a format string. A `%s` inside JSON quotes
is only valid when the source value is already proven JSON-safe by a named
operation or type contract.

Prefer one of these shapes:

- Encode with a schema-backed JSON codec.
- Write string content through an escaping operation such as
  `writeJsonEscapedStringBuffer`.
- Reject unsupported characters at the input boundary and document that
  invariant next to the buffer mutation operation.

Avoid this shape for user-editable content:

```semanticscript
storage local immutable itemFormat CNullTerminatedByteString "{\"title\":\"%s\"}\n"
call writeItemCall c.fprintf
arg writeItemCall stream fileHandle
arg writeItemCall format itemFormat
arg writeItemCall title titleBuffer
run writeItemCall
```

The operation is short, but the optimization deletes the encoding boundary.
Quotes, backslashes, newlines, and control bytes can corrupt the file format or
change the semantic value that will be loaded later.

`semlint.py` reports `rawJsonStringInterpolation` for conservative cases where
a JSON-like string literal places `%s` inside JSON quotes.

Fixed-format parsers should make their accepted producer format explicit in an
`invariant`. If a loader depends on offsets or object key order, say that it
only accepts the exact shape emitted by the matching saver.

`semlint.py` reports `fixedOffsetParserContract` when an operation declares
numeric `*ValueOffset` or `*FieldOffset` constants without an invariant naming
the exact fixed format or producer shape.

## Aggregate Pressure

Repeated scalar slots are acceptable for tiny compiler smoke tests, but they are
a maintenance smell in app code. Prefer records, arrays, or heap-backed buffers
once a behavior must be applied to more than one logical item.

Repeated names such as `slotOneTitle`, `slotTwoTitle`, and `slotThreeTitle`
force agents to make the same edit several times. Arrays keep the behavioral
surface in one loop, which is easier to lint, optimize, and patch consistently.

Derive allocation byte counts from logical capacities instead of mirroring the
same literal in two constants. This keeps later capacity changes from silently
under-allocating or over-allocating:

```semanticscript
storage local immutable todoCapacity CSignedInt64 128
storage local immutable doneFlagByteWidth CSignedInt64 1
call todoArrayBytesCall math.multiplyI64
arg todoArrayBytesCall left todoCapacity
arg todoArrayBytesCall right doneFlagByteWidth
run todoArrayBytesCall
bind todoArrayBytes CByteCount todoArrayBytesCall
```

For scalar state, keep widths consistent across direct assignment. `semlint.py`
reports `implicitScalarWidthDrift` for direct `set` operations that assign a
known 32-bit scalar into a known 64-bit scalar, or the reverse, without an
explicit widening or narrowing operation.

Keep C vararg format strings aligned with argument width. If a value is
`CSignedInt32`, use a 32-bit conversion such as `%d`, or explicitly widen the
value before using a 64-bit conversion such as `%lld`. The compiler cannot infer
the vararg contract from the format string at lowering time.

`semlint.py` reports `printfFormatWidthMismatch` when a `printf`/`fprintf`
format uses a 64-bit integer conversion while a known 32-bit integer value is
passed as the corresponding semantic argument.

For C-style APIs that report failure through a returned sentinel or status,
bind the return value and check it, or explicitly discard it with
`ignoreValue`. Do not add `bindError`/`branchIfError` to calls that are not
Result-shaped.

For owned resources, executable code needs executable cleanup. Use explicit
`c.free`/`c.fclose` calls when the compiler cannot lower the corresponding
host-call `defer`. Cleanup metadata is still useful for auditing, but it is not
a substitute for code that actually runs.

## Terminal State Lifecycle

Terminal ownership should be explicit. Do not hide the native cursor as a side
effect of every screen redraw. Split lifecycle operations from render
operations:

```semanticscript
operation hideCursor
operation clearScreen
operation showCursor
```

Call `hideCursor` once after startup succeeds, call `clearScreen` during
redraws, and call `showCursor` on exit paths that run after the cursor is
hidden. This gives agents and linters a clear cleanup contract to inspect.

`semlint.py` reports `terminalStateCleanup.missing` when an operation calls
`hideCursor` or `terminal.hideCursor` without a matching `showCursor` cleanup
call in the same operation.

## Result vs Status

Use `Result` when the caller must distinguish success data from typed failure:

```semanticscript
output saveTodosToJson Result Void SaveTodosError
```

Use an explicit status type when the operation is intentionally status-only:

```semanticscript
enum SaveStatus repr CSignedInt32
enumCase SaveStatus SaveSucceeded 0
enumCase SaveStatus SaveOpenFailed 1
```

Do not use bare `CSignedInt32` as a dumping ground for byte counts, OS statuses, exit codes, and typed semantic status. If several meanings share the same primitive shape, create aliases or enums so the source carries the distinction. Prefer enums for closed status domains; they give linters enough context to reject accidental comparisons through the wrong primitive width, such as sending a `CSignedInt32` status enum through an `I64` comparison target.

When an operation returns an enum-typed status, return enum cases at the
operation boundary:

```semanticscript
returnValue SaveWriteFailed
```

Do not return raw repr values such as `returnValue 2`. `semlint2.py` reports
`enumReturnUsesRawValue` for that shape because it erases the closed status
domain that the enum was introduced to provide.

Use math targets that match the value width. For C status bytes, key codes, and
pointer-loaded bytes, prefer:

```semanticscript
call doneCheckCall math.equalCSignedInt32
```

over routing those values through `math.equalI64`. `semlint2.py` reports
`mathOperandWidthDrift` when any math target receives an operand with a
different numeric shape. The compiler rejects those mismatches too; use a
width-specific math target or an explicit conversion operation.

For intentional integer width changes, call the conversion target directly:

```semanticscript
call widenCall math.signExtendCSignedInt32ToCSignedInt64
arg widenCall inputValue statusCode
```

Keep byte and flag helpers byte-shaped. A parser that reads a JSON `0`/`1`
field or a value loaded with `pointer.loadByte` should normally return
`CSignedInt32`, not `CSignedInt64`; indexes, lengths, capacities, and counters
remain the I64-shaped values.

Use domain aliases and enums once raw primitives start carrying application
state. Key input can use a domain alias over `CSignedInt32`, while closed modal
or screen state should be an enum:

```semanticscript
type TuiKeyCode CSignedInt32

enum ScreenMode repr CSignedInt64
enumCase ScreenMode ListMode 0
enumCase ScreenMode EditMode 1
```

This preserves the ABI width while giving agents and linters the semantic
context they need to avoid accidental raw-integer patches.

## Hoist Shared Immutables To Module Scope

When the same `storage local immutable NAME TYPE VALUE` line appears in three or
more operations, the values are no longer per-operation context — they are a
shared protocol or convention. Move them to `storage module immutable` at file
scope:

```semanticscript
# rationale: TUI key codes live above 0xFF (256) so a normalized key never
# collides with a raw byte returned by c.consoleGetch. Producer (readTuiKey)
# and consumer (main) share these values; declaring them once removes drift.
storage module immutable tuiKeyArrowUp TuiKeyCode 1001
storage module immutable tuiKeyArrowDown TuiKeyCode 1002
storage module immutable tuiKeyArrowLeft TuiKeyCode 1003
storage module immutable tuiKeyArrowRight TuiKeyCode 1004
```

Avoid this shape, where the same numeric protocol is encoded in two operations
without a shared source of truth:

```semanticscript
operation readTuiKey
storage local immutable normalizedArrowUp TuiKeyCode 1001    # producer

operation main
storage local immutable keyArrowUp TuiKeyCode 1001           # consumer
```

If one side's literal ever drifts, the bug is silent. The module-scope rule
keeps the protocol number declared once.

What stays local: per-operation offsets (`activeValueOffset 10`), per-operation
sentinels that are part of that operation's own state machine, or values whose
meaning is coupled to one operation's body. Module scope is for cross-operation
contract, not for a convenient way to share `0` and `1`.

`semlint2.py` reports `SS4401 styleDiscipline.duplicateLocalImmutableAcrossOps`
(T4 style, info severity) when a `storage local immutable` declaration with the
same name, type, and value appears in three or more operations. The diagnostic
includes a `hoistToModuleImmutable` fix candidate carrying the module-scope
declaration line to paste.

## ASCII Byte Literals

Storage lines that hold ASCII codepoints (`storage * immutable * CSignedInt32
V` for `V` in 32..126) should name the codepoint's role, not its byte value,
and either declare them at module scope or add a `# rationale:` comment that
identifies the character:

```semanticscript
# rationale: 34 = ASCII double quote; emitted by saveTodosToJson around titles.
storage module immutable asciiDoubleQuote CSignedInt32 34
storage module immutable asciiBackslash CSignedInt32 92
```

Avoid this shape, where the value-as-character mapping lives only in the
reader's head:

```semanticscript
storage local immutable quoteByte CSignedInt32 34
storage local immutable backslashByte CSignedInt32 92
```

`semlint2.py` reports `SS4402 styleDiscipline.magicAsciiByteLiteral` (T4 style,
info severity) when a `storage local immutable NAME CSignedInt32 V` declares a
printable-ASCII byte value (V in 32..126) without a `# rationale:` comment
naming the character. The diagnostic is suppressed when SS4401 already flags
the same name as a cross-operation duplicate so the same line isn't piled with
two style suggestions.

## Implicit Format Coupling

When one operation's body depends on byte offsets into another operation's
format string, the coupling is invisible at the call site. Document the
derivation next to the offsets so a future edit to the format string updates
the offsets in lockstep:

```semanticscript
# rationale: Offsets count bytes into the line written by saveTodosToJson's
# itemPrefixFormatText `{"active":1,"done":%d,"title":"`.
#   {"active":   = 10 bytes → activeValueOffset points at the active digit
#   ,"done":     = 9 bytes  → doneValueOffset = 10 + 9 = 19
#   ,"title":"   = 11 bytes → titleValueOffset = 19 + 11 = 30
# Any edit to itemPrefixFormatText must update these three offsets in lockstep.
storage local immutable activeValueOffset CSignedInt64 10
storage local immutable doneValueOffset CSignedInt64 19
storage local immutable titleValueOffset CSignedInt64 30
```

The `warning` line on the loader operation should also point at the produces
operation by name so an agent can navigate the coupling.

`semlint2.py` reports `SS4404 styleDiscipline.fixedOffsetParserNeedsRationale`
(T4 style, info severity) when an operation declares two or more `storage local
immutable *Offset` rows in a contiguous block without a preceding `# rationale:`
comment that names the emitter operation or the format-string derivation. The
rule recognises emitter-naming evidence like "emitted by", "format", "lockstep",
"coupled", or an operation name containing "saveTodos"-style stems. The
diagnostic asks the parser-side author to name the producer at the offset
declaration so a future edit to the format string is reviewable.

## Dead Initializers

A mutable storage line whose initializer is overwritten before the first read
is dead. Replace the initializer with the real first value:

```semanticscript
# rationale: readIndex starts at valueOffset so the loop begins past the
# `"title":"` prefix. The earlier zeroIndex initializer was dead.
storage local mutable readIndex CSignedInt64 valueOffset
```

Avoid this shape, where the initial value misleads a reader about where the
loop actually starts:

```semanticscript
storage local mutable readIndex CSignedInt64 zeroIndex
storage local mutable writeIndex CSignedInt64 zeroIndex
set local readIndex valueOffset
```

`semlint2.py` reports `SS4403 styleDiscipline.deadStorageInitializer` (T4
style, info severity) when a `storage local mutable NAME TYPE INIT` is
immediately followed by `set local NAME NEW` with no intervening read of
`NAME`. The diagnostic carries a `seedWithRealFirstValue` fix candidate
suggesting the storage row be reshaped to use the real first value directly.

## Cross-Cutting Control-Flow Invariants

When an invariant is enforced by routing multiple branches through a shared
label (`branch persistTodosThenLoop`), state the invariant in source on the
enclosing operation. The control-flow graph is not enough — a reader inspecting
one branch cannot see the rule:

```semanticscript
invariant main "Every code path that mutates todoCount, doneArray, or titlesArray exits through persistTodosThenLoop so todos.json is never stale after a successful render frame."
```

Without the explicit invariant, adding a new mutation path that forgets to
`branch persistTodosThenLoop` would silently desynchronize disk and memory
state. The invariant is the contract the goto pattern enforces.

## Capacity Relationships

When two capacity-like storage declarations are mathematically related (the
read buffer is twice the title buffer; the timeout is half the request budget;
the queue is one larger than the worker count), the relationship belongs in
an `invariant` line on the enclosing operation:

```semanticscript
invariant main "lineBufferBytes is sized at twice titleCapacity to absorb JSON escaping of quotes and backslashes; if titleCapacity grows, lineBufferBytes must grow with it or saveTodosToJson lines may exceed the read buffer on reload."
```

A literal `256 = 2 * 128` is invisible to grep; the invariant ties the values
together so a future capacity change does not silently break the relationship.

## Enum Discipline

Enums declared with `enum NAME repr TYPE` are not raw integers. The repr is a
lowering choice; the enum's identity is the named cases. Two anti-patterns
fight this:

**1. Comparing enum values through raw-width math targets.** The compiler
exposes `EnumName.equal` / `EnumName.notEqual` / `EnumName.lessThan` /
`EnumName.lessThanOrEqual` / `EnumName.greaterThan` /
`EnumName.greaterThanOrEqual` built-in domain methods. The compiler resolves
the enum's repr and dispatches to the matching `math.equal*` primitive — but
the source-level call expresses the enum, not the integer width.

```semanticscript
# Prefer:
call sameStatusCall SaveTodosStatus.equal
arg sameStatusCall left titleWriteStatus
arg sameStatusCall right SaveSucceeded

# Avoid:
call sameStatusCall math.equalCSignedInt32
arg sameStatusCall left titleWriteStatus
arg sameStatusCall right SaveSucceeded
```

`semlint2.py` reports `SS4405 styleDiscipline.enumReprComparison` (T4 style,
info severity) when any operand of a `math.equal*` / `math.notEqual*` /
`math.lessThan*` / `math.greaterThan*` call resolves to a declared enum type.
The fix candidate carries the exact `call <name> <EnumName>.<method>` line
to paste.

**2. Discarding enum returns.** An enum-typed return advertises a closed set
of distinct outcomes. `ignoreValue` claims all cases are interchangeable;
that claim must be load-bearing, not accidental.

```semanticscript
# Prefer one of:
bind saveStatus SaveTodosStatus saveCall
# rationale: every SaveTodosStatus case is acceptable here because the
# render frame already shows save state from the previous tick.
ignoreValue saveCall SaveTodosStatus

# Avoid bare:
ignoreValue saveCall SaveTodosStatus
```

`semlint2.py` reports `SS4406 styleDiscipline.enumResultDiscarded` (T4
style, info severity) when an `ignoreValue` row discards a value typed as
a declared enum. The diagnostic suggests either binding the result and
branching on the cases, or adding a `# rationale:` line justifying why all
cases are acceptable at the discard site.

The general rule: enum cases are the contract. Comparing or discarding
them must name the enum, not the underlying integer.

## Optimization Rule

Before optimizing a sequence, identify the semantic boundary:

1. Internal raw values may stay raw.
2. Operation outputs must be canonicalized or explicitly typed.
3. Failure-producing calls should either be handled locally or surfaced through `Result`.
4. A successful operation returning a scalar status should usually return zero.
5. Repeated `storage local immutable` across operations is a hoist signal, not a convenience.
6. State-bearing integer storage that takes a small named set of values is an enum waiting to be declared.
7. Enum comparisons use `EnumName.equal` (and the comparison family), not `math.equal*` directly.
8. Discarded enum returns require a `# rationale:` or a bind site, not silent `ignoreValue`.

This keeps optimized code patchable by agents and predictable for compiler lowering.

## Native HTTP Discipline (SS36xx)

The routed `target webServer` codegen path lowers a fixed surface of native
HTTP primitives. The three SS36xx linter rules pin contracts that the
runtime would otherwise enforce silently with a 404 / 500.

### Route method whitelist (SS3601 `invalidRouteMethod`)

`route SERVER METHOD PATH HANDLER` METHOD must come from
`{GET, HEAD, POST, PUT, PATCH, DELETE, OPTIONS}`. CONNECT and TRACE are
deliberately excluded — the blocking adapter has no tunneling semantics,
and TRACE would echo opaque request bytes back to clients. A route with
any other METHOD parses cleanly but **never matches a real request** —
the handler binding becomes dead code.

Optimization implication: do not optimize for a method the dispatcher will
never deliver. If a method outside the whitelist is genuinely required,
the work is on the runtime side (extending the dispatcher), not on the
handler side.

### Middleware contract (SS3602 `middlewareMissingResponseEffect`)

Operations bound via `routeMiddleware` MUST declare
`effect <op> write http.response*`. The dispatcher invokes middleware
**before** the route handler specifically so it can write response state
(headers, diagnostics). A read-only middleware op exists to write nothing,
which means the binding is the wrong hook — most likely a logging/metrics
job that belongs elsewhere.

```semanticscript
operation tracingMiddleware
input tracingMiddleware request HttpRequest
input tracingMiddleware response HttpResponse
output tracingMiddleware CSignedInt32
effect tracingMiddleware read http.request.path
effect tracingMiddleware write http.response    # SS3602 requires this
memory tracingMiddleware arena request
async tracingMiddleware no
useCapability tracingMiddleware httpRequestReader
useCapability tracingMiddleware httpResponseWriter
purpose tracingMiddleware "stamp X-Trace-Id on every response"
invariant tracingMiddleware "returns 0 to continue dispatch"
```

### Nullable-input null guard (SS3603 `unguardedHttpInput`)

A value bound from a nullable `http.request*` read must pass a
`pointer.isNull` guard before reaching the `body` argument of any
`http.response*` writer (or a transitive wrapper that forwards `body` to
one). The nullable reads are:

- `http.requestHeader`
- `http.requestQueryParam`
- `http.requestBodyText`
- `http.requestBodyBytes`
- `http.multipartPartText`
- `http.multipartPartBytes`
- `http.multipartPartFilename`
- `http.multipartPartContentType`

`http.requestMethod` and `http.requestPath` are **not** nullable for a
dispatched request — no guard needed when their values reach response body.

The guard pattern:

```semanticscript
call queryReadCall http.requestQueryParam
arg queryReadCall request request
arg queryReadCall name nameQueryName
run queryReadCall
bind queryValue CNullTerminatedByteString queryReadCall

call queryMissingCheckCall pointer.isNull
arg queryMissingCheckCall pointer queryValue
run queryMissingCheckCall
bind queryMissing Bool queryMissingCheckCall
branchIf queryMissing queryMissingPath

# happy path: queryValue is non-null and safe to pass to a response body
```

**Transitive wrapper detection.** A user op that takes a `body` input and
forwards it unchanged to `http.response*` is treated as a response body
writer by the linter (semlint2 walks to a fixed point). The gauntlet's
`writeTextResponse(response, status, body)` is the prototype case. You do
not need to repeat the guard inside each wrapper layer — guard once at
the binding site, and the lint follows the body through wrappers.

**Per-op opt-out marker.** If a route is intentionally pinning the
adapter's null-body 500 contract for regression coverage of the failure
path (the gauntlet's `/reflect/required-header-or-fail` is the canonical
example), declare:

```semanticscript
warning yourHandler "this route intentionally exercises the adapter null-body failure path; do not add a guard or this coverage disappears silently"
```

The phrase `null-body failure path` (or `null-body 500`) must appear
verbatim in the warning text — that's the marker `semlint2`
(`HTTP_NULL_GUARD_OPT_OUT_MARKERS`) matches. The marker is deliberately
specific so a generic "this might 500" warning cannot accidentally
silence the lint.

## Synchronous Lowering Of Async Constructs

Many concurrency-shaped verbs lower to synchronous code in the current
single-thread, single-process runtime. Optimizing those for "concurrency
overhead" is wasted work — the cost model is:

| Construct                       | Single-thread lowering                                         |
|---------------------------------|----------------------------------------------------------------|
| `start CALL` / `await CALL`     | Synchronous `run CALL` — `await` is a no-op                    |
| `taskGroup` + `startInGroup`    | Direct dispatch; child runs immediately, `awaitGroup` is a no-op |
| `workerPool` + `submitWork`     | Direct dispatch on the calling thread                          |
| `send` / `receive` on a channel | Single-slot alloca register pass between matched send/receive  |
| `lock` / `unlock`               | No-op (no contention possible)                                 |
| `select` + `selectCase`         | Ordinary branches, runtime dispatch deferred                   |
| `interval` + `awaitIntervalTick`| No-op (no timer runtime bound)                                 |
| `scheduler.sleep`               | Returns `i64 0` — no time passes                               |

These will become real concurrency when a scheduler runtime is bound;
until then, attempting to win throughput by parallelizing across them is
zero-sum. The structured-concurrency *shape* is still load-bearing for
agent reasoning, so keep the verbs — just don't expect them to spawn
threads.

## Compile-Time Asset Inlining

`literalSource NAME "path"` is resolved at compile time, not at runtime
(`_load_external_literals` runs between parse and codegen). Paths resolve
absolute first, then relative to the source-file's directory. Files that
fail to load leave the literal stub in place so the program still
compiles, but the literal's bytes will be zero — verify the path before
relying on the inlined data.

Optimization implication: don't add a runtime file-read for an asset that
could be inlined at compile time. The asset becomes part of the compiled
binary's `.rodata` (or equivalent), so cold-start cost is paid once at
link time, not on every request.

## Per-Call-Site JSON Buffer Lifetimes

`json.encode.<Primitive>` stack-allocates a per-call-site buffer that
lives for the lifetime of the enclosing operation:

- 32B for numerics (I64, CSignedInt32, Duration/Monotonic/UtcMilliseconds, Bool, F64/CFloat64/CFloat32)
- 256B for strings (String, CNullTerminatedByteString)

Two consequences:

1. **You can return / pass the encoded pointer to other ops in the same
   operation body.** It is not freed until the operation returns.
2. **You cannot return it to a caller and read it after the encoding op
   has returned** — the alloca is gone. If a caller needs to consume the
   encoded value across a function boundary, copy into caller-owned
   storage first.

For record-shaped `json.encode.RecordTypeName` / `json.decode.RecordTypeName`,
the current lowering is a zero-stub fallback (Partial per SYNTAX.md). Real
structural encoding awaits the `jsonCodec` runtime — until then, encode
records field-by-field through the primitive `json.encode.<Primitive>` calls.

## Math Operand Width Discipline

The `math.*I64` family requires both operands to already be i64-shaped.
Codegen does **not** widen or narrow implicitly. CByteCount, DurationMilliseconds,
MonotonicMilliseconds, UtcMilliseconds, CSignedByteCount, CAddressOffset,
CUnixSecondsSinceEpoch, CCpuClockTicks, CFileByteOffset, and Bool all
lower as i64 and are accepted as i64 operands by the math intrinsics.
Bool's lowering as i64 means math.equalI64 / math.greaterThanI64 over Bool
values work but are usually a code smell — use `math.equalCSignedInt32`
or the bool-specific branches instead.

For 32-bit comparisons, prefer `math.equalCSignedInt32` /
`math.lessThanCSignedInt32` over the I64 path — the i32 comparison avoids
routing status/count values through a needless extend, and lints under
SS4303 (`mathOperandWidthDrift`) flag the wrong width directly.

## Intrinsic / Runtime-Binding Fast Paths vs. Zero-Stub Fallback

`runtimeBinding OP TARGET` is real lowering for 12 targets in
`_RUNTIME_BINDING_MAP`. `intrinsicName OP NAME` is real LLVM lowering for
13 `arithmetic.*` targets in `_INTRINSIC_MAP`. Any other target falls
back to the dotted-target external-module **zero-stub** lowering — the
call compiles but returns 0 (or a null pointer), regardless of what the
op claims to do.

When optimizing a hot path, verify the call lowers to real code:

- `grep -n "if target ==" SemanticScript/compiler/semsc.py` for the
  explicit handlers
- `_RUNTIME_BINDING_MAP` and `_INTRINSIC_MAP` for the registered targets
- `runtimeBindingPrecondition` / `runtimeBindingFailure` lines on the op

A call you assumed was a fast intrinsic but is actually the zero-stub
fallback is the most common "this should be fast but isn't" surprise in
this compiler.

## Storage Form Hygiene

`const NAME TYPE VALUE` and `var NAME TYPE VALUE` are legacy
shorthands; new code should use the explicit storage forms (`storage
module immutable`, `storage local immutable`, `storage local mutable`,
`storage module mutable`, `sharedState process mutable`). The explicit
forms make scope, mutability, and ownership visible on every line, which
matters for the cross-op duplication detector (SS4401
`duplicateLocalImmutableAcrossOps`) — that rule's hoist suggestion is
always "promote to `storage module immutable`," not "promote to `const`".
