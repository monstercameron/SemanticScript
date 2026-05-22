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
argument writeJsonCall stream TYPE saveFileHandle
argument writeJsonCall format TYPE saveFormat
run writeJsonCall
ignore value source writeJsonCall type CSignedInt32
return value SaveSucceeded
```

Avoid this shape:

```semanticscript
bind value writeJsonResult CSignedInt32 writeJsonCall
return value writeJsonResult
```

That leaks a libc byte count into the operation boundary. A caller or backend may later interpret a nonzero scalar as failure-like control flow.

## Linter Guardrail

`semlint.py`, the canonical structured linter, reports
structured diagnostics under stable SS codes; the guardrails below cite the
codes that enforce each rule so agents can grep both this guide and the
linter's `kind` strings against the same vocabulary.

`semlint.py` reports `rawLibcReturnEscapesOperation` when an operation returns a binding produced by libc count/status calls such as `c.printf`, `c.fprintf`, `c.fread`, or `c.fwrite`.

The intended fix is one of:

- Map the raw value to an explicit domain status.
- Use `Result OkType ErrorType` and branch on the C call's real failure condition.
- Rename/retype the operation so the raw byte/count value is honestly the public result.

Do not declare `Result SomeValue Void` for helpers that cannot actually
`return error`. That shape makes callers use fallible syntax for an infallible
operation and can interact badly with the current user-operation ABI, where the
success payload is the concrete return slot. Use a plain output instead:

```semanticscript
output copyStringBuffer CSignedInt64
```

`semlint.py` reports `resultVoidErrorWithoutFailurePath` when an operation
declares `Result A Void` without any `return error` path.

## App Boundary Rule

Treat `c.*` as a backend boundary, not as the normal application API.
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

Direct `c.*` calls are acceptable in low-level runtime/backend modules,
stdlib implementation files, compiler smoke tests, and backend bring-up samples.
They should be avoided in top-level apps and user-facing examples unless the
top-level SemanticScript API is still missing.

This keeps the dependency direction clean: apps depend on SemanticScript
contracts, stdlib/runtime code owns the temporary C interop layer, and the backend
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

- Encode whole typed values with `json.stringify.<TypeName>`.
- Build dynamic object/array responses through `JsonDocument` mutators and
  serialize once with `json.serializeDocument`.
- Write string content through an escaping operation such as
  `writeJsonEscapedStringBuffer` only while migrating legacy call sites.
- Reject unsupported characters at the input boundary and document that
  invariant next to the buffer mutation operation.

Avoid this shape for user-editable content:

```semanticscript
storage local immutable itemFormat CNullTerminatedByteString "{\"title\":\"%s\"}\n"
call writeItemCall c.fprintf
argument writeItemCall stream TYPE fileHandle
argument writeItemCall format TYPE itemFormat
argument writeItemCall title TYPE titleBuffer
run writeItemCall
```

The operation is short, but the optimization deletes the encoding boundary.
Quotes, backslashes, newlines, and control bytes can corrupt the file format or
change the semantic value that will be loaded later.

`semlint.py` reports `rawJsonStringInterpolation` for conservative cases where
a JSON-like string literal places `%s` inside JSON quotes. The intended repair
is `json.stringify.<TypeName>` for typed request/response records, or
`json.createEmptyDocument` plus `json.serializeDocument` when the shape is built
incrementally.

Fixed-format parsers should make their accepted producer format explicit in an
`invariant`. If a loader depends on offsets or object key order, say that it
only accepts the exact shape emitted by the matching saver.

`semlint.py` reports `fixedOffsetParserContract` when an operation declares
numeric `*ValueOffset` or `*FieldOffset` constants without an invariant naming
the exact fixed format or producer shape.

## Bounded String Accumulators

Repeated `c.strcat` into a fixed-size accumulator is bounded but still
quadratic. Each append rescans the bytes already written, so a loop that appends
N fragments pays for the prefix again on every iteration. The capacity check may
make the code memory-safe, but it does not make the shape a good hot-path
optimization.

`semlint.py` reports SS3203 `performanceDiscipline.stringAccumulatorAppendInLoop`
when `c.strcat`/`c.strncat` style appends appear inside a back-edge loop.
It also reports SS3205 `performanceDiscipline.snprintfI32OffsetWithoutWidening`
when a `c.snprintf` byte count is added directly to an i64 cursor; widen it
with `math.signExtendCSignedInt32ToCSignedInt64` first.

Prefer a cursor-based builder:

```semanticscript
storage local mutable writeOffset CSignedInt64 zeroIndex
call copyChunkCall memory.copy
argument copyChunkCall destination TYPE outputBuffer
argument copyChunkCall destinationOffset TYPE writeOffset
argument copyChunkCall source TYPE chunkBuffer
argument copyChunkCall byteCount TYPE chunkLength
run copyChunkCall
call nextOffsetCall math.addI64
argument nextOffsetCall left TYPE writeOffset
argument nextOffsetCall right TYPE chunkLength
run nextOffsetCall
bind value nextOffset CSignedInt64 nextOffsetCall
set local writeOffset nextOffset
```

Keep one explicit remaining-capacity check before each copy and write the final
NUL once. If a `strcat` accumulator stays because the fragment count is tiny and
not data-dependent, document that bound in an `invariant` so later patches do
not turn the bounded case into a quadratic request-size path.

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
argument todoArrayBytesCall left TYPE todoCapacity
argument todoArrayBytesCall right TYPE doneFlagByteWidth
run todoArrayBytesCall
bind value todoArrayBytes CByteCount todoArrayBytesCall
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
`ignore value`. Do not add `bind error`/`branch error` to calls that are not
Result-shaped.

For owned resources, executable code needs executable cleanup. Use explicit
`c.free`/`c.fclose` calls when the compiler cannot lower the corresponding
host-call `defer`. Cleanup metadata is still useful for auditing, but it is not
a substitute for code that actually runs.

Heap allocation failure is also executable control flow. Every heap-producing
call (`memory.allocate`, `c.malloc`, allocator-backed string builders, or
runtime setup allocators) must bind the returned pointer, check it with
`pointer.isNull`, and branch to an OOM path before the first dereference or
copy. The OOM path must return a typed error/status or cleanly unwind to the
caller; a warning comment, optimistic use, or crash-by-null-dereference is not a
valid failure contract.

For C heap allocators, `semlint.py` reports SS3305
`memoryDiscipline.uncheckedHeapAllocation` unless each `c.malloc`, `c.calloc`,
or `c.realloc` call has both `bind error` and `branch error`.

Partial setup failures must close any handles already opened. For SQLite,
that means a successful `sqlite3_open` followed by a failed schema creation,
pragma setup, prepare, or migration step must call the matching close operation
before returning failure. Prefer a shared cleanup label for setup code so
every failure after handle acquisition passes through the same executable close
path. A `defer` row is enough only when the current backend lowers it on that
failure path; otherwise write the close call directly.

`semlint.py` reports SS3905
`resourceLifecycle.sqliteDatabaseFailureCleanupMissing` when a
`sqlite.openDatabase` success handle can reach a later setup failure label
without `sqlite.closeDatabase`. It reports SS3906
`resourceLifecycle.sqliteStatementFinalizeMissing` when
`sqlite.prepareStatement` lacks a same-operation `sqlite.finalizeStatement`
defer or explicit cleanup call.

## Fixed-Capacity Row Mutations

Fixed row editors should treat "row count unchanged" as a refused insert/split,
not as a successful no-op. When a mutator such as `insertEmptyRowAt` or
`splitRowAt` returns the prior `activeRowCount`, branch out before moving the
cursor, marking the file dirty, or writing into the row.

`semlint.py` reports SS3207
`performanceDiscipline.rowCountMutationUnchecked` when a fixed-row mutator
returns a row count but the caller does not compare that result to the prior
`activeRowCount` and branch on the full-buffer path.

## GUI Event Mutation Boundaries

Keep add/create handlers separate from selection handlers. A handler that reads
`gui.listBoxSelectedIndex` is usually confirming or updating an existing
selection; appending a new list item in that same handler creates a hidden
growth path where repeated "complete selected" clicks keep extending the list.

`semlint.py` reports SS3206
`performanceDiscipline.selectedListAppendInHandler` when one operation both
reads `gui.listBoxSelectedIndex` and calls `gui.listBoxAppendItem`.

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
return value SaveWriteFailed
```

Do not return raw repr values such as `return value 2`. `semlint.py` reports
`enumReturnUsesRawValue` for that shape because it erases the closed status
domain that the enum was introduced to provide.

Use math targets that match the value width. For C status bytes, key codes, and
pointer-loaded bytes, prefer:

```semanticscript
call doneCheckCall math.equalCSignedInt32
```

over routing those values through `math.equalI64`. `semlint.py` reports
`mathOperandWidthDrift` when any math target receives an operand with a
different numeric shape. The compiler rejects those mismatches too; use a
width-specific math target or an explicit conversion operation.

For intentional integer width changes, call the conversion target directly:

```semanticscript
call widenCall math.signExtendCSignedInt32ToCSignedInt64
argument widenCall inputValue TYPE statusCode
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

`semlint.py` reports `SS4401 styleDiscipline.duplicateLocalImmutableAcrossOps`
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

`semlint.py` reports `SS4402 styleDiscipline.magicAsciiByteLiteral` (T4 style,
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

`semlint.py` reports `SS4404 styleDiscipline.fixedOffsetParserNeedsRationale`
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

`semlint.py` reports `SS4403 styleDiscipline.deadStorageInitializer` (T4
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
argument sameStatusCall left TYPE titleWriteStatus
argument sameStatusCall right TYPE SaveSucceeded

# Avoid:
call sameStatusCall math.equalCSignedInt32
argument sameStatusCall left TYPE titleWriteStatus
argument sameStatusCall right TYPE SaveSucceeded
```

`semlint.py` reports `SS4405 styleDiscipline.enumReprComparison` (T4 style,
info severity) when any operand of a `math.equal*` / `math.notEqual*` /
`math.lessThan*` / `math.greaterThan*` call resolves to a declared enum type.
The fix candidate carries the exact `call <name> <EnumName>.<method>` line
to paste.

**2. Discarding enum returns.** An enum-typed return advertises a closed set
of distinct outcomes. `ignore value` claims all cases are interchangeable;
that claim must be load-bearing, not accidental.

```semanticscript
# Prefer one of:
bind value saveStatus SaveTodosStatus saveCall
# rationale: every SaveTodosStatus case is acceptable here because the
# render frame already shows save state from the previous tick.
ignore value source saveCall type SaveTodosStatus

# Avoid bare:
ignore value source saveCall type SaveTodosStatus
```

`semlint.py` reports `SS4406 styleDiscipline.enumResultDiscarded` (T4
style, info severity) when an `ignore value` row discards a value typed as
a declared enum. The diagnostic suggests either binding the result and
branching on the cases, or adding a `# rationale:` line justifying why all
cases are acceptable at the discard site.

The general rule: enum cases are the contract. Comparing or discarding
them must name the enum, not the underlying integer.

## Project Metadata Embedded In The Executable

Declare project metadata in the project's `build.sem` tape so executable
identity lives beside target/runtime/output configuration instead of inside
`main.sem`. `build.sem` also registers module folders; module files keep their
own `module`, `importModule`, and `export*` contract rows. On `--emit-exe` the
compiler generates a transient Windows
`VERSIONINFO` resource, compiles it with `llvm-rc` (or `windres` if present),
and links the compiled `.res` from the managed `build/resources/` directory
into the final PE — no separate metadata file ships with the program. The
fields are then visible from Windows Explorer → Properties → Details, from
PowerShell `(Get-Item file.exe).VersionInfo`, and via `version.dll`'s
`VerQueryValue` for arbitrary user keys.

```semanticscript
project TaskForgeTui
target console
runtime native 1
entry console main

version "1.0.0.0"
publisher "Earl Cameron"
description "SemanticScript TaskForge TUI — keyboard-driven console todo app."
copyright "Copyright (c) 2026 Earl Cameron."
productName "TaskForge TUI"
internalName "todo"
originalFilename "taskforge_tui.exe"
comments "Built from apps/taskforge-tui/main.sem by the SemanticScript compiler."
metadata "BuildSource" "apps/taskforge-tui/main.sem"
metadata "RuntimeContract" "native 1"

registerModule taskForgeTui app.taskforge_tui "."
```

Mapping to Windows VERSIONINFO StringFileInfo entries:

| SemanticScript verb | VERSIONINFO key | Default if omitted |
|---|---|---|
| `version "A.B.C.D"` | `FileVersion`, `ProductVersion`, `FILEVERSION` / `PRODUCTVERSION` | `0.0.0.0` |
| `publisher "..."` | `CompanyName` | empty |
| `description "..."` | `FileDescription` | project name |
| `copyright "..."` | `LegalCopyright` | empty |
| `productName "..."` | `ProductName` | project name |
| `internalName "..."` | `InternalName` | project name |
| `originalFilename "..."` | `OriginalFilename` | basename of emit-exe path |
| `trademark "..."` | `LegalTrademarks` | empty |
| `comments "..."` | `Comments` | empty (entry omitted) |
| `metadata "key" "value"` | arbitrary user key in the same string-table | n/a, repeatable |

Toolchain notes:

- The compiler probes `llvm-rc` on `PATH` and at
  `C:\Program Files\LLVM\bin\llvm-rc.exe`, then `windres`. Honors
  `$SEMSC_WINRC` for an explicit override.
- The generated `.rc` is UTF-8 with BOM; non-ASCII characters in metadata
  strings (em-dash, smart quotes, accents) are passed through with
  `/C 65001` so the resource compiler interprets the high-bit bytes as
  UTF-8.
- On non-Windows platforms the metadata is still parsed and indexed (so
  IDE tooltips, agents, and future macOS/Linux emitters can read it) but
  no resource is generated and the link proceeds normally.
- If no resource compiler is available the build emits a warning and
  links without VERSIONINFO; the exe still runs.

The `metadata "key" "value"` form is the escape hatch for arbitrary
publisher-specific fields (`BuildSource`, `BuildDate`, `GitCommit`, etc.).
Custom keys land in the same StringFileInfo block as the standard fields
and are readable from `VerQueryValue` queries against
`\StringFileInfo\040904b0\<key>`.

## Build-Time Icon Registry Embedded In The Executable

Icons declared in `build.sem` are baked into the same Windows VERSIONINFO
resource section as the metadata above. Every fact about every image gets
its own row so the relationship between source PNGs and what ships inside
the `.exe` is grep-able and machine-checkable:

```semanticscript
iconRoleDefinition applicationPrimary   "Primary application icon …"
iconRoleDefinition applicationSecondary "Secondary application icon …"

icon         todoPrimaryIcon
iconRole     todoPrimaryIcon applicationPrimary
iconPurpose  todoPrimaryIcon "Stylized 'T' on a teal background …"

iconImage         todoPrimaryAt16
iconImageGroup    todoPrimaryAt16 todoPrimaryIcon
iconImagePath     todoPrimaryAt16 "assets/icons/icon-16.png"
iconImageFormat   todoPrimaryAt16 png
iconImageWidth    todoPrimaryAt16 16
iconImageHeight   todoPrimaryAt16 16
iconImageScale    todoPrimaryAt16 1
iconImageDepth    todoPrimaryAt16 bits32
iconImagePlatform todoPrimaryAt16 any
iconImagePurpose  todoPrimaryAt16 "Smallest cell — Explorer details column …"

# iconImageAt32 / At48 / At256 follow the same row shape …
```

At `--emit-exe` time the compiler:

1. Walks every `iconImage` whose `iconImageGroup` resolves to an `icon`
   with `iconRole applicationPrimary`.
2. Filters to images with `iconImagePlatform any` or `windows`.
3. Sorts by width and packs the source PNGs into a transient
   PNG-encoded multi-size `.ico` (Vista+ supported, preserves alpha).
4. Emits `1 ICON "<tmp>.ico"` ahead of the VERSIONINFO block in the
   generated `.rc`, hands the file to `llvm-rc`, and the resulting
   `.res` is linked into the PE.

After link the icon is readable from Windows Explorer thumbnails, the
taskbar, the Alt-Tab thumbnail row, and via
`[System.Drawing.Icon]::ExtractAssociatedIcon` from PowerShell. macOS
(`macos`) and Linux (`linux`) platform tokens are parsed and indexed for
future emitters; nothing is embedded for them yet.

## Residue-Free Build Default

The intermediate `.rc`, `.res`, and `.ico` produced for VERSIONINFO and
icon embedding live in a system tempdir by default. After `llvm-rc` and
clang finish, the temp files are deleted — the resource bytes survive
only inside the linked `.exe`'s PE resource section. A clean build
contains nothing but the executable (plus `.ll` if IR persistence is
on):

```text
build/
  taskforge_tui.exe
  todo.ll
```

To inspect the generated `.rc` or the packed `.ico` (e.g. when an icon
isn't appearing or a custom metadata key isn't readable), opt in via the
build tape:

```semanticscript
keepResources    taskForgeTui yes
# or, with an explicit directory:
resourcesDir     taskForgeTui "build/resources"
```

Or per-invocation via the CLI:

```text
python compiler/semsc.py build.sem --emit-exe build/taskforge_tui.exe --keep-resources
python compiler/semsc.py build.sem --emit-exe build/taskforge_tui.exe --resource-dir /tmp/icon-debug
```

CLI flags override `build.sem` declarations. The default is intentionally
strict: a release build leaves no filesystem residue, so the question
"what shipped in the binary?" is answered only by reading the binary
itself, not by a stale `.rc` left behind on a developer's machine.

## Optimization Rule

Before optimizing a sequence, identify the semantic boundary:

1. Internal raw values may stay raw.
2. Operation outputs must be canonicalized or explicitly typed.
3. Failure-producing calls should either be handled locally or surfaced through `Result`.
4. A successful operation returning a scalar status should usually return zero.
5. Repeated `storage local immutable` across operations is a hoist signal, not a convenience.
6. State-bearing integer storage that takes a small named set of values is an enum waiting to be declared.
7. Enum comparisons use `EnumName.equal` (and the comparison family), not `math.equal*` directly.
8. Discarded enum returns require a `# rationale:` or a bind site, not silent `ignore value`.

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
argument queryReadCall request TYPE request
argument queryReadCall name TYPE nameQueryName
run queryReadCall
bind value queryValue CNullTerminatedByteString queryReadCall

call queryMissingCheckCall pointer.isNull
argument queryMissingCheckCall pointer TYPE queryValue
run queryMissingCheckCall
bind value queryMissing Bool queryMissingCheckCall
branch if condition queryMissing target queryMissingPath

# happy path: queryValue is non-null and safe to pass to a response body
```

**Transitive wrapper detection.** A user op that takes a `body` input and
forwards it unchanged to `http.response*` is treated as a response body
writer by the linter only when it declares
`responseBodyForwarder OP bodyInputName` (semlint walks declared forwarders to
a fixed point). The gauntlet's `writeTextResponse(response, status, body)` is
the prototype case. You do not need to repeat the guard inside each wrapper
layer. Guard once at the binding site, and the lint follows the body through
declared wrappers.

`semlint.py` reports SS3615 `webserver.responseBodyForwarderMissing` when an
operation forwards one of its inputs to `http.responseText`,
`http.responseBytes`, or `http.responseSseEvent` without the declaration. This
keeps helper functions from hiding nullable request values from SS3603.

**Per-op opt-out marker.** If a route is intentionally pinning the adapter's
null-body 500 contract for regression coverage of the failure path (the
gauntlet's `/reflect/required-header-or-fail` is the canonical example),
declare the explicit opt-out row:

```semanticscript
pinsNullBodyFailurePath yourHandler "intentional regression coverage of the native adapter null-body 500 path"
```

`semlint.py` reports SS3606 when the rationale is missing or empty. The legacy
prose marker inside `warning OP "..."` is still honored for one deprecation
cycle, but it trips SS3605 so migrations can replace it with the explicit row.

### Response writer ownership

`http.response*` writers and user wrappers around them must own or copy every
body, header name, header value, and content-type pointer that can outlive the
handler stack frame. A handler is allowed to run cleanup immediately after the
writer returns:

```semanticscript
call responseCall http.responseText
argument responseCall response TYPE response
argument responseCall status TYPE okStatus
argument responseCall body TYPE scratchBody
run responseCall
call scratchFreeCall c.free
argument scratchFreeCall pointer TYPE scratchBody
run scratchFreeCall
return value okStatus
```

That shape is safe only if the response writer has already copied `scratchBody`
into response-owned storage or has completed the send before returning. Do not
optimize response writes by storing borrowed pointers into handler-local
buffers, SQLite row buffers, request arenas, or heap allocations that a later
`defer`/cleanup path can release. If copying is too expensive for a binary body,
make ownership explicit with a transfer operation whose contract says the
handler must not free the buffer after the call.

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
| `scheduler.sleep` runtimeBinding| Unsupported until an explicit scheduler runtime is bound        |

Note: declaring `scheduler.sleep` as a runtimeBinding is now compile-blocking
unless an explicit scheduler runtime owns that behavior; the old compiler
no-op was removed from the runtimeBinding fast path.

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

## JSON Serialization Lifetimes

Prefer the high-level JSON surface over direct stack-buffer formatting:

- `json.stringify.<TypeName>` for primitive and record-shaped values.
- `json.serializeDocument` after `json.createEmptyDocument` and document
  mutators for dynamic object/array construction.

Legacy `json.encode.<Primitive>` stack-allocates a per-call-site buffer that
lives only for the lifetime of the enclosing operation:

- 32B for numerics (I64, CSignedInt32, Duration/Monotonic/UtcMilliseconds, Bool, F64/CFloat64/CFloat32)
- 256B for strings (String, CNullTerminatedByteString)

Two consequences:

1. **You can return / pass the encoded pointer to other ops in the same
   operation body.** It is not freed until the operation returns.
2. **You cannot return it to a caller and read it after the encoding op
   has returned** — the alloca is gone. If a caller needs to consume the
   encoded value across a function boundary, copy into caller-owned
   storage first.

Do not build new record encoders around `json.encode.RecordTypeName` /
`json.decode.RecordTypeName`; those names are the legacy partial surface.
Use `json.stringify.<RecordTypeName>` and `json.parse.<RecordTypeName>` for
schema-backed values, or the document CRUD API when fields are assembled in a
loop. When `json.serializeDocument` needs caller-owned scratch, keep the scratch
buffer owned by the current operation and copy or write the returned `JsonText`
before the scratch storage is released.

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

`runtimeBinding OP TARGET` is real lowering only for pure ABI shims in
`_RUNTIME_BINDING_MAP` such as cstring length/compare and memory copy.
`intrinsicName OP NAME` is real LLVM lowering for 13 `arithmetic.*`
targets in `_INTRINSIC_MAP`. Any other target falls
back to the dotted-target external-module **zero-stub** lowering — the
call compiles but returns 0 (or a null pointer), regardless of what the
op claims to do.

Policy or domain runtimeBinding targets are intentionally not compiler
semantics. Retry-delay calculation, metrics increment behavior, lock token
sentinels, scheduler sleeps, calendar predicates, and UTF-8 validation should
be normal SemanticScript operation bodies or explicit native runtime calls.
Known legacy policy targets fail at executable codegen instead of silently
returning a compiler stub.

When optimizing a hot path, verify the call lowers to real code:

- `grep -n "if target ==" SemanticScript/compiler/semsc.py` for the
  explicit handlers
- `_RUNTIME_BINDING_MAP` and `_INTRINSIC_MAP` for the registered targets
- `runtimeBindingPrecondition` / `runtimeBindingFailure` lines on the op

A call you assumed was a fast intrinsic but is actually the zero-stub
fallback is the most common "this should be fast but isn't" surprise in
this compiler.

## Storage Form Hygiene

`const NAME TYPE VALUE` and `var NAME TYPE VALUE` are removed
shorthands; new code should use the explicit storage forms (`storage
module immutable`, `storage local immutable`, `storage local mutable`,
`storage module mutable`, `sharedState process mutable`). The explicit
forms make scope, mutability, and ownership visible on every line, which
matters for the cross-op duplication detector (SS4401
`duplicateLocalImmutableAcrossOps`) — that rule's hoist suggestion is
always "promote to `storage module immutable`," not "promote to `const`".

## Route Handler Input Names Are An ABI Contract

Every operation reachable from a `route SERVER METHOD PATH HANDLER`
binding (and every operation bound via `routeMiddleware`) MUST declare
its `HttpRequest` input under the canonical name `request` and its
`HttpResponse` input under the canonical name `response`. The native
dispatcher binds positionally (`[HttpRequest, HttpResponse,
CSignedInt32]`) so a handler with `req`/`resp` *compiles and runs*,
but every other name-based lookup in the toolchain breaks silently:

- `semlint`'s SS3603 transitive-body walk resolves the response slot
  by looking for `argument <call> body <type> <slot>` against the `body` input
  name.
- `narrative_citations_for_operation` walks per-input narrative edges
  by input name.
- Agents reading the source infer the request/response role from the
  name — `req`/`resp` reads as "ported from JavaScript/Go" and is
  semantically ambiguous.

This is enforced by `semlint` SS3609 `routeHandlerInputNameMismatch`,
graded ERROR with `blocksCompile=True`. The rule cites the route
binding site alongside the offending input line so a reader sees both
"why this op is held to the contract" and "where the contract is
violated." The fix is a 1-token rename and the fix candidate is
auto-applicable.

## Method-Polymorphic Route Handlers

A single handler can be registered for multiple HTTP methods on the
same path — the gauntlet's `bodySizeHandler` is bound to both
`POST /reflect/body-size` and `PUT /reflect/body-size`. There is no
`routeShared HANDLER METHODS_LIST PATH` verb today; method
polymorphism is expressed by repeating the `route` row with the same
handler name.

When the handler actually inspects the request method (e.g., to branch
between POST and PUT semantics), it MUST declare the matching effect:

```semanticscript
operation methodAwareHandler
input methodAwareHandler request HttpRequest
input methodAwareHandler response HttpResponse
output methodAwareHandler CSignedInt32
effect methodAwareHandler read http.request.method  # required when inspecting method
effect methodAwareHandler write http.response
```

If the handler ignores the method and treats the body identically
across verbs (as `bodySizeHandler` does), `read http.request.method`
is NOT required — and adding it would be a false claim that
SS3603-style effect-coverage rules would honor as truth. Lint guidance:
declare the effect when, and only when, an `http.requestMethod` call
appears in the handler body. The companion `routeMiddleware` /
`routeTimeout` coverage entries collapse POST+PUT to one entry per
path, so the multiplicity is asymmetric: route rows repeat, middleware
and timeout rows don't.

## Middleware Return Contract

Middleware ops bound through `routeMiddleware` declare:

```semanticscript
output gauntletMiddleware MiddlewareControl
...
return value continueMiddlewareControl
```

`MiddlewareControl` is a compiler-registered enum backed by `CSignedInt32`.
`continueMiddlewareControl` runs the route handler. `shortCircuitMiddlewareControl`
skips the handler and sends the response already written by the middleware.
The dispatcher makes a missing short-circuit body visible as a 500 response
instead of treating it as success.

`semlint.py` reports SS3610 `middlewareReturnNotMiddlewareControl` when an
operation bound via `routeMiddleware` still declares `output OP CSignedInt32` or
another non-`MiddlewareControl` output. This is an ERROR with
`blocksCompile=True`, even though the source-level enforcement still lives in
the linter rather than in the parser.

## Cross-Document References

Several `warning OP "..."` and `invariant OP "..."` lines cite spec
rows by anchor (`SYNTAX.md#webServer`, `SYNTAX.md#routeMiddleware`).
There is no first-class `tracks OP "anchor"` verb; the references are
prose. The discipline:

- Use the literal anchor text that appears in `SYNTAX.md` (e.g.,
  `#routeMiddleware` not `#middleware`).
- The drift guard `TestHttpTargetSourceOfTruth` (`test_semlint.py`)
  asserts every `http.*` target from `semsc.py` is mentioned in
  `SYNTAX.md`. For other cross-doc references, manual review is the
  only enforcement — add `grep -F 'SYNTAX.md#anchor' apps/` to the
  review checklist if you add a new tracking citation pattern.
- If a tracking citation breaks (anchor renamed, row removed), fix
  the source row rather than silently updating the reference; the
  citation is a contract that says "this code is shaped by THAT spec
  decision," and stale citations decay faster than stale comments.

This pattern is intentionally informal: a new `tracks` verb would only
pay off when the cross-doc citation count exceeds the dozen or so
currently in flight. Until then, prose + manual grep is cheaper than
a verb nobody adopts.

## HTTP Target Source-Of-Truth

The native HTTP target surface lives in three places:

1. `semsc.py` — the dispatch block (`if target == "http.responseText":`
   and friends), each marked with the SOURCE-OF-TRUTH banner.
2. `semlint.py` — `HTTP_METHOD_WHITELIST`,
   `NON_NULLABLE_HTTP_REQUEST_READS`, `NULLABLE_HTTP_REQUEST_READS`,
   `HTTP_RESPONSE_BODY_WRITERS`, `HTTP_RESPONSE_OTHER_WRITERS`, and
   the `ALL_NATIVE_HTTP_TARGETS` union.
3. `SYNTAX.md` — the two `http.requestMethod, …` and
   `http.responseText, …` umbrella rows.

`TestHttpTargetSourceOfTruth` in `test_semlint.py` parses semsc.py
for every `"http.X"` literal and asserts the set equals
`ALL_NATIVE_HTTP_TARGETS`. A second assertion checks every dispatch
target appears in SYNTAX.md. A third checks the four classifier sets
are pairwise disjoint so membership-based decisions in SS3603 /
SS3601 are unambiguous.

When you add a new `http.*` target to the runtime, update all three
sites in lockstep. The drift test will tell you if you missed one;
don't silence the test, fix the drift.

## Void Output Operations Use `return void`

The user-op ABI returns i32 even for operations declared
`output OP Void` / `output OP CVoid` — the type system maps Void to
i32 at the return slot, and codegen tolerates any sentinel value.
That tolerance has a cost: a Void op that ends with `return value
someI32Zero` says one thing at the output line ("no caller-actionable
value") and another at the return site ("here is an integer
sentinel"), and a future agent reading either half in isolation has
to recognise the ABI quirk to reconcile them.

`return void` is the explicit form:

```semanticscript
operation addCommonHeaders
input addCommonHeaders response HttpResponse
output addCommonHeaders Void
effect addCommonHeaders write http.response
memory addCommonHeaders arena request
async addCommonHeaders no
useCapability addCommonHeaders httpResponseWriter
purpose addCommonHeaders "stamp diagnostic headers; no caller-actionable status"
invariant addCommonHeaders "Void output means the op never reports a recoverable error"
label startAddCommonHeaders
# ... header writes ...
return void
```

Codegen still emits the i32-zero sentinel under the hood, but the
source matches the semantic contract. The compiler rejects
`return void` on non-Void outputs so the verb cannot become a backdoor
around the result-contract checker.

`semlint` SS3612 `voidReturnValueShouldBeReturnVoid` flags Void-output
ops that still use `return value NAME`. The fix candidate is
auto-applicable: drop the `storage local immutable zeroSentinel
CSignedInt32 0` line and rewrite `return value zeroSentinel` →
`return void`. SS3612 is WARNING by default (the older form may still compile
correctly); `--strict` promotes it to fatal for CI pipelines that
want source-level honesty enforced.

## Narrative Citations Should Cite Stable Identifiers

When a `purpose` / `invariant` / `warning` / `rationale` line refers
to another file, cite by **stable identifier**, not by line number.
The stable choices, in order of preference:

1. **Rule ID** — `SS3603 unguardedHttpInput`. Rule IDs are assigned
   once and never renumbered.
2. **Spec anchor** — `SYNTAX.md#routeMiddleware`. Anchors track the
   spec row; row reordering doesn't change the anchor.
3. **Function name** — `semsc.py`'s `_check_route_methods`. Function
   names rename rarely and break loudly when they do.
4. **Grep-anchor** — a quoted unique string that finds the cited
   code: `"if target == \"http.responseText\""`. Survives line drift
   as long as the literal stays in the source.

The brittle form is:

```semanticscript
# DON'T:
invariant gauntletMiddleware "see semsc.py:3674 for the lowering"
warning requiredHeaderHandler "asserted at test_http_runtime_gauntlet.py:273-279"
```

Both citations drift the moment the referenced file gets an insertion
above the cited line — and they drift silently, because nothing in
the build verifies that `semsc.py` line 3674 is still the function
the narrative meant.

The stable form is:

```semanticscript
# DO:
invariant gauntletMiddleware "see semsc.py's pointer.isNull lowering"
warning requiredHeaderHandler "asserted by the `/reflect/required-header-or-fail` block in test_http_runtime_gauntlet.py"
```

`semlint` SS3613 `narrativeReferencesLineNumber` flags `<file>:<line>`
and `line <NN>` patterns inside narrative text. The diagnostic
suggests function-name and rule-ID replacements. Like SS3612, it's
WARNING by default; promote to fatal under `--strict` if narrative
durability is a CI requirement.

## Multipart Content-Type Nullability

`http.multipartPartContentType` returns NULL when the part exists but
has no `Content-Type` header in its `Content-Disposition` block.
Passing NULL to `http.responseBytes`'s `contentType` argument is
safe — the native runtime defaults a NULL `contentType` to
`"application/octet-stream"`. So this pattern is well-defined:

```semanticscript
bind value uploadFileContentType CNullTerminatedByteString uploadFileContentTypeReadCall
# safe to pass straight to http.responseBytes — runtime defaults NULL → octet-stream
argument uploadFileBytesResponseCall contentType TYPE uploadFileContentType
```

What is NOT safe is using `uploadFileContentType` for anything OTHER
than the response writer's `contentType` argument — e.g., binding it
to a variable that gets compared against a string, or splicing it
into a format buffer. The NULL would propagate and crash. If you
need to inspect the content type, guard with `pointer.isNull` first
and substitute an explicit default at the SemanticScript layer.

This contract is documented in `multipartFileBytesHandler`'s
invariant. The gauntlet's multipart test fixture sends an explicit
`Content-Type: application/x-gauntlet` so the test verifies the
non-NULL path, but the NULL → octet-stream default path is reachable
for clients that omit the header.
