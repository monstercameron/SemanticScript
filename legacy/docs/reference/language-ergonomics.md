# Language Ergonomics Boundary

SemanticScript allows ergonomic shortcuts only when the shortcut still expands
to stable row-shaped data. The source must remain patchable by line-oriented
tools, and each observable fact must still have a durable row that diagnostics
can cite.

## Checked Calls

The accepted compact form for the common fallible-call pattern is:

```text
runChecked CALL ok VALUE TYPE error ERROR TYPE else LABEL
```

`runChecked` expands the normal checked-call shape for one prepared call:

```text
run CALL
bind ok VALUE TYPE CALL
bind error ERROR TYPE CALL
branch error source CALL target LABEL
```

It intentionally does not absorb `call` or `argument` rows. Call target and
argument facts remain separate rows because they are the part most frequently
patched by tools, inspected by `slice`, and checked by argument-name/type
diagnostics.

Known limits:

- The call must already be declared with `call` and any needed `argument` rows.
- Async-only runtime bindings use `start`/`await`, not `runChecked`.
- Retry-managed calls still need the explicit checked pattern because retry
  lowering has additional control-flow metadata.
- `runChecked` covers one call execution row; sibling `run` rows for the same
  fallible call are still independently checked.

## Call Execution Model

`call` declares a named call site. `argument` rows attach typed inputs to that
call site. `run` executes the prepared call site. A loop that needs to execute
the same target repeatedly must jump back above the `call`/`argument`/`run`
sequence, not only above the `run` row, so the call record is reconstructed for
each iteration.

```text
label readLoop
call stepCall sqlite.stepStatement
argument stepCall statement SqliteStatement listStatement
run stepCall
bind ok stepResult SqliteStepResult stepCall
...
jump target readLoop
```

Argument names are part of the source contract for humans, lint, docs, and
future stricter validation. Current lowering dispatches user-operation
arguments by callee input order after dropping opaque context inputs, so source
should keep both order and names aligned with the callee signature. Treat a
name/order mismatch as a bug even if an older compiler accepts it.

Fallible calls store two facts after execution: an ok value and an error
condition. `branch error source CALL target LABEL` tests the call site's error
condition. A preceding `bind error ERROR TYPE CALL` names the error payload for
handling or wrapping with `makeError`; it is not the branch predicate.

Disposition rows depend on the target contract:

- Infallible value target: `bind value VALUE TYPE CALL` or
  `ignore value source CALL type TYPE`.
- Fallible value target: `bind ok VALUE TYPE CALL`, usually paired with
  `bind error ERROR TYPE CALL` and `branch error source CALL target LABEL`.
- Void target: `ignore void source CALL`.
- Fallible discard: `ignore ok source CALL type TYPE`, usually paired with the
  error bind/branch rows.

`ignore ok` currently repeats the discarded success type so diagnostics and
patch tools can preserve the result contract even when no value name exists.
`ignore void` has no type because there is no success payload.

## Rejected Sugar

These forms are deliberately not syntax:

- Inline argument sugar on `call` rows. It hides argument names/types inside a
  variable-width row and makes per-argument diagnostics harder to anchor.
- `run CALL orElse LABEL`. It hides the success/error bind names and types that
  downstream rows use.
- Multi-bind rows for reading several values from one statement. Each bound
  value needs its own row so lifetime, unused-bind, and column-buffer diagnostics
  can point at the exact slot.
- Inheriting effects, authority, memory, or async metadata from callers. Those
  declarations are part of an operation contract; implicit inheritance would
  make the callee's required authority depend on a distant caller.
- `ignore ok source CALL` without a type. The current grammar keeps discarded
  success payload type explicit until diagnostics can infer and display it
  consistently.

When boilerplate is mechanical but still row-compatible, prefer structured
repair tools over new syntax. `sem fix --plan --json` emits local rename edits
for the naming-discipline rules `SS4001`, `SS4002`, and `SS4003`.

## DSL Islands

The one-fact-per-row thesis allows embedded DSL islands only when the boundary
itself is a named row and the island is typed as source data. Current examples
are `sql body NAME`, `jsonBody NAME`, and `html body template NAME`. The body
text belongs to the named storage/template fact; dynamic values still cross the
boundary through explicit rows such as `sqlite.bind*` arguments or
`html.hydrate.*` arguments.

The storage row before an island is the typed handle. It deliberately has no
inline value; the island fills that named handle:

```text
storage module immutable createTaskSql SqlText
sql body createTaskSql
  INSERT INTO tasks(title) VALUES (?1);
```

Island extent is indentation-based. The island body continues while subsequent
lines are indented under the island header and ends at the next column-0 row.
Keep the next SemanticScript row dedented to column 0, and avoid accidental
dedents inside long SQL/HTML/JSON bodies.

This keeps the row format human-editable for contracts and tool-generated for
large repetitive shapes. Humans can edit the named boundary and the surrounding
dataflow; tools should generate repetitive call/argument/bind rows when the
volume becomes high.

## Effects And Authority

`effect OP ACTION PATH` says the operation performs an observable action.
`authority OP ACTION PATH` says the operation is permitted to perform it.
`capability NAME PATH ACTION` is a grantable resource edge, and
`useCapability OP NAME` connects an operation to that grant.

The rows are often identical in small programs because the operation both
declares and authorizes its own external behavior. They differ when a module
exports reusable capability grants, when a wrapper operation should expose an
effect but not define the grant itself, or when tooling audits an operation that
has authority broader than the effects it actually performs.

Do not declare compute-only effects. Declare effects for observable resources:
console, filesystem, network, database, heap, shared state, process, HTTP
request/response, GUI, and similar external surfaces.

## Coercion Boundaries

SemanticScript has role aliases over primitive and pointer shapes. Current
lowering allows compatible role aliases to cross `bind` and `argument` rows
when the lowered representation is the same. Common examples:

- `SqliteText`, `HttpRequestValue`, `HttpHeaderValue`, `HttpTextBody`, and
  `String` are all string-pointer shaped.
- `OpaquePointer` can feed string-ish role aliases at argument sites when the
  callee owns the interpretation, as in bounded buffers passed to
  `c.snprintf`, SQLite text binding, response bodies, and bcrypt hash buffers.
- Integer role aliases such as `HttpStatusCode`, `SqliteRowId`, and
  `HttpBodyLength` lower through their declared integer representation.

This is a representation compatibility rule, not a parsing or validation rule.
Use explicit helper calls when the bytes need decoding, escaping, length checks,
or ownership transfer. If an alias boundary matters for review, keep the role
name in the bind or argument row closest to the API call.

## Project Shape

Console programs use an explicit `entry console OPERATION`. Routed
`target webServer` programs do not use an entry row; `webServer`, `route`,
`staticRoute`, `webServerStartup`, and `webServerShutdown` rows define the
runtime entrypoints and the native dispatcher synthesizes the process entry.

In project mode, `build.sem` owns build identity and source selection:

- `buildProject` is the build-tape handle used by project-scoped rows.
- `project` is the display/compiler bridge project name.
- `modulePath` is the package path.
- `registerModule` maps a module path to a source file or folder.
- The source file's `module` row declares the module being compiled.
- Route/server rows live in module source, not in `build.sem`.

When a `build.sem` is the entrypoint, its build rows take precedence over
source-file `project`/`target`/`entry` headers for project selection. Keep those
headers out of module files unless they are standalone examples.

## Tooling Signals

`sem eval FILE` is the one-off JIT runner for snippets and single files. `sem
run`/`sem build` operate on project surfaces and may discover `build.sem`.
Native runtime adapters such as SQLite, HTTP, bcrypt, GUI, and network are not
linked by eval; the eval payload reports `native-runtime-unavailable` before
launch when such targets are present.

`sem check --json` uses `ok` for "no compile-blocking diagnostics." A payload
can still contain warnings or advisories. Read the diagnostic counts and the
source-lane status (`ok`, `ok-with-warnings`, `lint-diagnostics`,
`compiler-error`, or `tool-error`) instead of treating the boolean as a clean
tree gate.

`sem docs get NAME --json` returns a `matches` array because the same spelling
can name an operation target, type, enum, constant, or compatibility alias. For
exact target lookups, use the first exact match. For enum and record discovery,
prefer the type payload when available and fall back to `syntax-inventory.md`
until `docs get TYPE --members` lands.

## Enum And Status Predicates

Use standard-library predicates when a status enum has one. For SQLite step
results, branch through the `standard.sqlite` helpers instead of comparing raw
representation integers or hand-written constants:

```text
call doneCheckCall sqlite.stepResultIsDone
argument doneCheckCall stepResult SqliteStepResult stepResult
run doneCheckCall
bind value stepDone Bool doneCheckCall
```

Enums declared with `enum NAME repr TYPE` still lower through their
representation, but helper predicates keep executable code on the standard
contract instead of hard-coded representation integers such as SQLite row/done
status codes or JSON value-kind codes.

## Label Roles

Error-edge labels are role signals, not grammatical tense. The linter accepts
failure labels such as `allocationFailed`, past-tense labels ending in `ed`, and
recovery labels such as `reject`, `rollback`, or `redirect`. Non-error branch
targets should use the domain action they represent rather than forcing an
`Error` noun into a label.
