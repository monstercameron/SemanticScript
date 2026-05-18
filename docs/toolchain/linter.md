# Linters

SemanticScript has two linter tracks:

- `SemanticScript/linter/semlint.py`: current standalone source linter.
- `SemanticScript/linter/semlint2.py`: structured refinement linter with tiers,
  citations, fix candidates, and agent-oriented output.

The compiler also has an internal lint pass behind `semsc.py --lint`, but editor
and CI integrations should prefer the standalone linter entry points.

## semlint.py

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
python SemanticScript/linter/semlint.py SemanticScript/sem/fizzbuzz.sscript --format json --fail-on none
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
group/endGroup balance
duplicate domain literals
semantic comment prefix checks
```

## semlint2.py

Run one file:

```powershell
python SemanticScript/linter/semlint2.py SemanticScript/sem/fizzbuzz.sscript
```

Structured JSON:

```powershell
python SemanticScript/linter/semlint2.py SemanticScript/sem/fizzbuzz.sscript --format json
```

Agent-oriented output:

```powershell
python SemanticScript/linter/semlint2.py SemanticScript/sem/fizzbuzz.sscript --format agent
```

Emit diagnostics as SemanticScript-shaped records:

```powershell
python SemanticScript/linter/semlint2.py SemanticScript/sem/fizzbuzz.sscript --format sem-record
```

Filter:

```powershell
python SemanticScript/linter/semlint2.py SemanticScript/sem --tier T3 --code SS0101
```

semlint2 tiers:

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

## semlint2 Check Families

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
bind-then-ignore
memory heap contradictions
missing allocation sources
unpaired allocate/free calls, accepting defer metadata or explicit c.free
stack-limit overruns
record alignment
zero-length arrays
small-list inline capacity without spill allocator
unawaited task groups and work submissions
locks without cleanup
selects without cases
async calls without timeout/cancel boundary
file handles not closed, accepting defer metadata or explicit close calls
guard tokens without release
circular type aliases
incomplete JSON codecs
argument arity and type mismatch
arg rows that reference undeclared values
enum outputs returning enum cases rather than raw repr values
math operand width drift across I64, CSignedInt32, and F64 targets
unresolved references
duplicate declarations
```

## App-Scale Checks

The stable `semlint.py` surface includes conservative app-scale checks for JSON
serialization boundaries, fixed-format parser contracts, and direct scalar-width
drift. The structured `semlint2.py` track should keep equivalent checks as it
absorbs more app-facing rules.

## Serialization Checks

Linters treat JSON formatting as a boundary, not as ordinary text output. A
string format that writes `%s` content inside JSON quotes is flagged because the
source value may need escaping before it crosses the serialization boundary.

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

Math lowering is exact: `math.*I64` receives I64-shaped values,
`math.*CSignedInt32` receives CSignedInt32-shaped values, and F64 math receives
F64-shaped values. The compiler does not widen or narrow these operands
implicitly. Use width-specific math targets such as `math.lessThanCSignedInt32`
for C status/count values, or insert an explicit conversion operation before the
math call. For signed i32/i64 changes, use
`math.signExtendCSignedInt32ToCSignedInt64` or
`math.truncateCSignedInt64ToCSignedInt32`.

When a closed status domain is modeled as an enum, semlint2 treats enum cases as
typed values and checks the enum repr against the target signature so a status
enum does not silently degrade back into a raw integer. semlint2 reports
`mathOperandWidthDrift` when any math target receives an operand with a
different numeric shape; this diagnostic is compile-blocking because codegen
rejects the same mismatch.

## Editor Integration

The VS Code extension defaults to `semlint.py`. Set:

```json
{
  "semanticScript.linter.engine": "semlint2"
}
```

The extension parses both legacy JSON diagnostics and semlint2 structured JSON.
For refined future syntax, the extension can skip current `semlint.py`
diagnostics by default because the current executable linter intentionally lags
some research syntax.
