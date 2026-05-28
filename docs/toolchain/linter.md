# Linters

SemanticScript has one canonical standalone linter:

- `SemanticScript/linter/semlint.py`: structured diagnostics with stable
  `SS<code>` identifiers, tiers, citations, fix candidates, and
  agent-oriented output.

The compiler also has an internal lint pass behind `semsc.py --lint`, but editor
and CI integrations should prefer the standalone linter entry points.

## Basic Usage

Run one file:

```powershell
python SemanticScript/linter/semlint.py SemanticScript/sem/fizzbuzz.sscript
```

Run a directory:

```powershell
python SemanticScript/linter/semlint.py SemanticScript/sem --summary
```

JSON output for editor integration:

```powershell
python SemanticScript/linter/semlint.py SemanticScript/sem/fizzbuzz.sscript --format json
```

Strict CI:

```powershell
python SemanticScript/linter/semlint.py SemanticScript/sem --strict
```

Rule families include:

```text
unknown verbs and missing arguments
flat line-shape checks
naming checks
call lifecycle checks
unknown call/label references
explicit failure and success dataflow
operation contract checks
Result-with-Void-error helper checks
console effect declaration checks
async timeout/cancellation checks
resource cleanup hints, including explicit-close recognition
filesystem read/write effect precision from file modes and file I/O calls
file open/close effect checks
terminal hidden-cursor cleanup checks
raw libc return escape checks
printf/fprintf integer format-width mismatch checks
raw JSON string interpolation checks
fixed-format parser invariant checks
implicit scalar width drift checks
unknown capability references, including imported capability typos
hierarchical capability coverage, such as http.request covering http.request.path
route metadata selector checks for routeTimeout and routeMiddleware
routed native HTTP handler ABI checks
native HTTP call argument checks for request readers, multipart readers, text writers, byte writers, SSE-event writers, JSON writers, and header writers
nullable HTTP reader flow checks before non-null response/header sinks
response header ordering (`SS3619`): `http.responseHeader` must run before
  the first response body/file/redirect writer, because the native response
  latches staged headers when the body writer runs
group/endGroup balance
duplicate domain literals
semantic comment prefix checks
```

Naming-discipline advisories `SS4001`, `SS4002`, and `SS4003` are T4 style
signals, not build blockers. They are also mechanical: `sem fix --plan --json`
emits local `replaceLine` edits for adding the `Call`, `Error`, and `Failure`
role suffixes inside the enclosing operation, and `sem patch --dry-run` should
be used before applying them on a busy worktree.

## Structured Output

Run one file:

```powershell
python SemanticScript/linter/semlint.py SemanticScript/sem/fizzbuzz.sscript
```

Structured JSON:

```powershell
python SemanticScript/linter/semlint.py SemanticScript/sem/fizzbuzz.sscript --format json
```

Agent-oriented output:

```powershell
python SemanticScript/linter/semlint.py SemanticScript/sem/fizzbuzz.sscript --format agent
```

Emit diagnostics as SemanticScript-shaped records:

```powershell
python SemanticScript/linter/semlint.py SemanticScript/sem/fizzbuzz.sscript --format sem-record
```

Filter:

```powershell
python SemanticScript/linter/semlint.py SemanticScript/sem --tier T3 --code SS0101
```

semlint tiers:

| Tier | Meaning | Default intent |
|---|---|---|
| `T0` | Parse / grammar | non-overridable error |
| `T1` | Spec violation | non-overridable error |
| `T2` | Lowering invariant | non-overridable error |
| `T3` | Refinement gap | warning by default |
| `T4` | Style / convention | info by default |

Diagnostic records include:

```text
tier
code
kind
severity
primary span
subject
message
intent slogan
citations
fix candidates
confidence
effort
blocksCompile
```

## semlint Check Families

The structured linter currently checks:

```text
unused calls, labels, capabilities, error cases, mutable storage
partial retry policies and trust boundaries
literals without digest/encoding
operation metadata gaps
shared-state protection
effects without capabilities
unknown verbs
vague names
unused bind slots, consts, and inputs
hidden failures
Result fallible calls vs C sentinel/status value disposition
sibling metadata drift
undeclared body effects
unknown error variants
dead stores
allocation in loops
loop-invariant pure calls (SS3208): a side-effect-free arithmetic/comparison
  call inside a loop whose every argument is loop-invariant (not rebound or
  `set`-mutated in the loop body), so it recomputes the same value each
  iteration and should be hoisted above the loop header
string accumulator appends in loops
snprintf byte counts used as i64 offsets without explicit widening
non-constant printf-family format strings (`SS3310`)
GUI selection handlers that also append list items
fixed-capacity row mutations without unchanged-count branches
bind-then-ignore
memory heap contradictions
missing allocation sources
unchecked heap allocation disposition for c.malloc/c.calloc/c.realloc/c.alignedAlloc
unpaired allocate/free calls, accepting defer metadata, `memory.releaseMemoryBytes`, or explicit c.free
stack-limit overruns
record alignment
zero-length arrays
small-list inline capacity without spill allocator
unawaited task groups and work submissions
locks without cleanup
selects without cases
async calls without timeout/cancel boundary
file handles not closed, accepting defer metadata or explicit close calls
SQLite database setup failures without close cleanup
SQLite statements without finalize cleanup
SQLite column text/blob/name pointers used after same-statement buffer overwrite
SQL body islands bound to non-`SqlText` storage or containing interpolation holes
syntax-island errors (`html body template`, `jsonBody`, `sql body`) with body-line primary spans when available
guard tokens without release
circular type aliases
incomplete JSON codecs
argument arity and type mismatch
argument rows that reference undeclared values
enum outputs returning enum cases rather than raw repr values
math operand width drift across Int64, Int32, and Float64 targets
unresolved references
duplicate declarations
```

## App-Scale Checks

The `semlint.py` surface includes conservative app-scale checks for JSON
serialization boundaries, fixed-format parser contracts, direct scalar-width
drift, cursor-based string builders, heap/SQLite cleanup, GUI event mutation
boundaries, and native HTTP wrapper contracts.

Some hardening rules intentionally remain in the standalone linter even when
the compiler has matching strict-lint coverage. Treat `blocksCompile=True`
diagnostics such as `SS3610 middlewareReturnNotMiddlewareControl` as release
blockers, but verify new parser/codegen hardening with `semsc.py --parse-only`
without `--lint` before marking a TODO item as always-on compiler behavior.

## SQLite Column Pointers

`sqlite.columnText`, `sqlite.columnBlob`, and `sqlite.columnName` return
SQLite-owned pointers tied to the prepared statement that produced them. The
value is not a copied SemanticScript string. On the same statement, the next
pointer-returning column read, `sqlite.stepStatement`, `sqlite.resetStatement`,
or `sqlite.finalizeStatement` can invalidate the bytes before a later call uses
the bound value. A different prepared statement does not clobber this pointer.

`semlint.py` reports SS3113
`resourceLifetime.columnTextOverwrittenBeforeUse` when a borrowed column
pointer is read, another same-statement read/step/reset happens, and the older
value is then consumed. Use or copy each borrowed text/blob/name before the next
same-statement invalidating operation; use by-value readers such as
`sqlite.columnInt64` where possible.

## Serialization Checks

Linters treat JSON formatting as a boundary, not as ordinary text output. A
string format that writes `%s` content inside JSON quotes is flagged because the
source value may need escaping before it crosses the serialization boundary.

Legacy JSON builder/finder calls are also blocked with replacement guidance:
`SS3624` points JsonBuilder call chains to `json.stringify.<TypeName>` for typed
values or to `json.createEmptyDocument` plus `json.setObjectField*` /
`json.appendArrayElement*` and `json.serializeDocument` for document mutation.
`SS3625` points `json.find*` / `json.hasField` to `json.createDocument`,
`json.cursorAtPath` or `json.objectFieldAt`, and typed cursor readers such as
`json.cursorString`.

High-signal patterns:

```text
{"title":"%s"}
{"message":"%s"}
```

Acceptable fixes:

- Replace the raw interpolation with a schema-backed JSON codec.
- Route the value through an operation named for escaping, for example
  `writeJsonEscapedStringBuffer`.
- Reject unsupported characters at input and document the exact accepted
  character set in the mutation operation invariant.

Fixed-offset parsers should also carry an invariant that names the exact
producer format they accept. If a parser depends on object key order, field
spacing, or hard-coded offsets, that contract should be visible in source and
reported when missing.

## Width Checks

Math lowering is exact: `math.*Int64` receives Int64-shaped values,
`math.*Int32` receives Int32-shaped values, and Float64 math receives
Float64-shaped values. The compiler does not widen or narrow these operands
implicitly. Use width-specific math targets such as `math.lessThanInt32`
for C status/count values, or insert an explicit conversion operation before the
math call. For signed i32/i64 changes, use
`math.signExtendInt32ToInt64` or
`math.truncateInt64ToInt32`.

When a closed status domain is modeled as an enum, semlint treats enum cases as
typed values and checks the enum repr against the target signature so a status
enum does not silently degrade back into a raw integer. semlint reports
`mathOperandWidthDrift` when any math target receives an operand with a
different numeric shape; this diagnostic is compile-blocking because codegen
rejects the same mismatch.

## Editor Integration

The VS Code extension defaults to `semlint.py`. Set:

```json
{
  "semanticScript.linter.engine": "semlint"
}
```

The extension parses both legacy JSON diagnostics and semlint structured JSON.
For refinement-only files that are not executable by the current compiler yet,
the extension can skip linter diagnostics when
`semanticScript.linter.skipFutureSyntax` is enabled.
