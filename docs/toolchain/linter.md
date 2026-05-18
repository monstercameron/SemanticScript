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
console effect declaration checks
async timeout/cancellation checks
resource cleanup hints
raw libc return escape checks
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
sibling metadata drift
undeclared body effects
unknown error variants
dead stores
allocation in loops
bind-then-ignore
memory heap contradictions
missing allocation sources
unpaired allocate/free calls
stack-limit overruns
record alignment
zero-length arrays
small-list inline capacity without spill allocator
unawaited task groups and work submissions
locks without cleanup
selects without cases
async calls without timeout/cancel boundary
file handles not closed
guard tokens without release
circular type aliases
incomplete JSON codecs
argument arity and type mismatch
unresolved references
duplicate declarations
```

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
