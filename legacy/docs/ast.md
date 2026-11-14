# SemanticScript AST

This document describes the current parser and AST model implemented by
`SemanticScript/compiler/semsc.py`. It is a developer reference for compiler,
linter, formatter, editor, and runtime work. The public syntax inventory remains
`docs/reference/syntax-inventory.md`; the language-design narrative is `docs/semantic-script.md`.

Current scope:

- `SemanticScript/compiler/semsc.py` is the maintained reference compiler.
- `SemanticScript/shared/call_contracts.py` owns call fallibility facts shared by
  the compiler, linter, and CLI tests.
- `SemanticScript/sem/feature_tests/` is the focused compiler feature corpus.
- There is no maintained SemanticScript-written compiler path in the active
  tree.

## Design Model

SemanticScript source is a semantic tape: one row states one fact or action.
The AST therefore stays mostly flat. It records declarations, operation header
facts, operation body rows, syntax islands, source locations, and import origins;
it does not build a nested expression tree.

Every parsed row keeps enough source context for diagnostics:

- parsed stream line number;
- raw row text;
- origin path and line before import flattening when available;
- row verb and normalized argument tokens.

## Lexical Model

Each physical line is either:

```text
declaration row       project, module, type, record, operation, storage, ...
context row           input, output, effect, memory, authority, purpose, ...
action row            call, argument, run, bind, ignore, set, makeError, ...
control row           label, branch, jump, return
syntax-island row     html body template TEMPLATE, jsonBody NAME, sql body NAME
comment row           # rationale:, # security:, # group, # endGroup, ...
```

Rows are tokenized as whitespace-delimited tokens with quoted strings preserved
as one token. Sigil-prefixed row verbs, dotted row verbs, equals-sign key/value
rows, and replaced legacy row verbs are rejected before permissive parsing can
hide them as metadata.

## Top-Level Program

The `Program` object records the current source unit:

```text
project_name
module_name
targets
entry
consts
mutable_globals
type_aliases
errors
operations
records
enums
web_servers
html_templates
json_bodies
record_json_constants
storage_declarations
type_metadata
capabilities
codecs
validators
policies
resources
imports and exported symbol maps
source_lines and source_origins
```

Build metadata, icons, native resource metadata, and regular `BuildPlan`
records are also stored on `Program` so build tapes and regular app sources can
share the same parser.

## Top-Level Rows

The current executable and tooling surface includes:

```semanticscript
project NAME
target console|webServer|windowsGui|...
runtime NAME VERSION
entry console OPERATION
module dotted.name
mode capturedOutputReplay
languageMode strictExecutable|refinedSyntax|permissiveExecutable

import ALIAS MODULE_PATH
importOperation LOCAL ALIAS EXPORTED
importType LOCAL ALIAS EXPORTED
importError LOCAL ALIAS EXPORTED
importCapability LOCAL ALIAS EXPORTED
importConstant LOCAL ALIAS EXPORTED

type NAME UNDERLYING
type NAME result ok OK_TYPE error ERROR_TYPE
error NAME
errorCase ERROR VARIANT UNDERLYING_TYPE

storage module immutable NAME TYPE VALUE
storage module mutable NAME TYPE VALUE
storage local mutable NAME TYPE VALUE

record NAME
field RECORD FIELD TYPE
recordFieldJsonName RECORD FIELD "jsonKey"
recordFieldJsonOmitWhen RECORD FIELD POLICY

enum NAME repr TYPE
enumCase ENUM CASE VALUE

operation NAME
webServer NAME
route SERVER METHOD PATH HANDLER

html template NAME
html body template NAME
jsonBody NAME
sql body NAME
jsonCodec NAME
codec NAME ATTRS...
validator NAME
policy NAME
resource NAME
capability NAME
```

Rows that are parseable but not fully executable remain explicit metadata. Under
`languageMode strictExecutable`, unknown lowercase top-level rows are rejected
unless the file opts into `refinedSyntax`.

## Operation Headers

Operation header rows repeat the operation name so each row remains
self-describing when copied, sorted, or shown in diagnostics:

```semanticscript
operation main
input operation main request HttpRequest
output operation main ExitCode
effect main write console.stdout
authority main write console.stdout
memory main heap auto
async main no
purpose operation main "Describe why this operation exists."
invariant operation main "State a property tooling can preserve."
```

The parser stores header facts on the owning `Operation` and also preserves the
row in `Operation.lines` for linter and codegen passes.

## Operation Body Rows

Executable body rows are flat `Statement` records. The current source forms are:

```semanticscript
label LABEL

call CALL TARGET
argument CALL PARAM TYPE VALUE
timeout CALL DURATION
cancelOn CALL TOKEN
run CALL
runChecked CALL ok OK_NAME OK_TYPE error ERROR_NAME ERROR_TYPE else LABEL
start CALL
await CALL

bind value NAME TYPE CALL
bind ok NAME TYPE CALL
bind error NAME TYPE CALL

ignore value source CALL type TYPE
ignore ok source CALL type TYPE
ignore error source CALL
ignore void source CALL

makeError NAME ERROR.VARIANT SOURCE_VALUE
set memory NAME VALUE
set storage NAME VALUE

branch if condition CONDITION target LABEL
branch error source CALL target LABEL
branch else target LABEL
jump target LABEL

return value VALUE
return ok VALUE
return error VALUE
return void
```

`runChecked` is syntax sugar for the common checked call shape: it runs the
call, binds the success and error names, branches to the failure label when the
call's error condition is true, and otherwise falls through.

## Call Lifecycle

A call is assembled from:

```text
call CALL TARGET
argument CALL PARAM TYPE VALUE
run CALL or runChecked CALL ...
bind/ignore rows that account for every result channel
branch error source CALL target LABEL when the call can fail
```

Call targets are classified by `SemanticScript/shared/call_contracts.py`:

- ordinary value calls expose the `value` channel;
- result-shaped calls expose `ok` and `error`;
- fallible ordinary calls expose `value` and `error`;
- void calls expose `void`.

The compiler records each call as a dictionary with target, named arguments,
declared argument types, source lines, result value, error value, error
condition, and optional handle slots for resources such as SQLite handles.

## Return Model

`return` is variant-bearing source syntax:

```semanticscript
return value statusCode
return ok responseBody
return error parseError
return void
```

The operation `output` row determines which variant is legal:

- `output operation OP TYPE` uses `return value VALUE`;
- `output operation OP Result OK ERROR` uses `return ok VALUE` and
  `return error VALUE`;
- `output operation OP Void` or `Void` uses `return void`.

For the current user-operation ABI, `Void` still lowers to an internal zero
sentinel, but source code should use `return void` so the semantic contract is
visible.

## Control Flow

Labels lower to LLVM basic blocks. Conditional rows have one target and
otherwise fall through:

```semanticscript
branch if condition shouldStop target done
branch else target loopBody

branch error source parseBodyCall target parseFailed
```

`branch else target LABEL` must immediately follow a `branch if` or
`branch error` row. `jump target LABEL` is the unconditional branch form.

## Storage And Mutation

`storage` rows declare named slots or constants:

- `storage module immutable` maps to a module constant;
- `storage module mutable` maps to an LLVM internal global plus load/store;
- `storage local mutable` maps to an operation-local mutable slot.

Mutation is scope-qualified:

```semanticscript
set memory localCounter nextCounter
set storage moduleCounter nextCounter
```

The compiler rejects the old unscoped assignment row because the scope affects
both lowering and ownership checks.

## JSON Bodies

`jsonBody NAME` starts a column-0 JSON syntax island. Indented lines after it
belong to the JSON body until the next non-empty column-0 SemanticScript row.

The body must attach to a preceding storage declaration with no inline value:

```semanticscript
storage module immutable healthBody JsonText
jsonBody healthBody
  {
    "status": "ok",
    "ready": true
  }
```

Compiler behavior:

- validates the body with Python's strict JSON parser;
- rejects non-standard constants such as `NaN` and `Infinity`;
- stores the original body lines and a compact canonical JSON string;
- binds `JsonText` storage to the canonical string;
- type-checks record targets, including required fields, unknown keys, nested
  records, `recordFieldJsonName`, and `recordFieldJsonOmitWhen`;
- records typed record constants in `Program.record_json_constants`.

For tooling, JSON object keys and values are distinct JSON tokens inside the
syntax island even though the compiler stores the validated result as Python
data plus canonical text.

## HTML Bodies

`html body template TEMPLATE` starts an indentation-sensitive HTML/SSX island.
Dynamic holes are double-brace bare names or dotted record-field paths such as
`{{titleText}}` or `{{profile.title}}`. The old single-brace form, such as
`{titleText}`, is a hard error with guidance to use `{{titleText}}`. Single
braces in JavaScript, CSS, and object literals remain literal unless they are
exactly the old hole syntax. The compiler records the raw body lines, inferred
dynamic arguments, and source lines on the `HtmlTemplate`.

String holes are escaped according to text or quoted-attribute sink context.
URL-bearing attributes (`href`, `src`, `action`, `formaction`, and `poster`)
require the compiler/std-owned `HtmlSafeUrl` role alias; plain `String` is
rejected in those sinks.
`HtmlFragment`, `HtmlTrustedFragment`, and `HtmlDocument` insert raw content only
in text-content positions.

## SQL Bodies

`sql body NAME` starts a column-0 SQL syntax island. Indented lines after it
belong to the SQL body until the next non-empty column-0 SemanticScript row. The
body binds to a preceding `storage module immutable NAME SqlText` declaration
with no inline value.

Compiler behavior:

- stores the SQL text with the syntax-island base indentation removed;
- rejects empty text, NUL bytes, unterminated SQL quoted text/comments, and
  `{hole}` interpolation syntax;
- records the leading SQL verb, placeholder count, and statement count;
- binds the `SqlText` storage to the preserved null-terminated SQL text;
- keeps dynamic values out of the source text: callers use `?` placeholders and
  explicit `sqlite.bind*` rows.

## Records And Enums

Records are parsed into `Record` objects with field order, field types, JSON
names, and omit policies. Current executable lowering uses flattened field
slots rather than a public struct ABI.

Enums are parsed into `Enum` objects with a representation type and named cases.
The compiler also auto-registers runtime enums such as HTTP middleware control
and selected GUI enums when needed.

## Defer And Cleanup

Cleanup rows are part of the operation tape:

```semanticscript
defer NAME TARGET ARGS...
deferRunOn NAME all|ok|error
deferOrder NAME reverseRegistration
```

Supported cleanup targets lower before `return value`, `return ok`,
`return error`, `return void`, and fall-through exits. SQLite cleanup targets
use stored handle slots so cleanup remains SSA-safe across failure labels.
Unsupported cleanup targets are preserved as metadata until a runtime lowering
exists.

## Concurrency-Shaped Rows

The parser accepts structured concurrency, channels, locks, worker pools,
intervals, and select-shaped rows. Some have synchronous fallback lowering;
others are metadata or structural stubs that register names so later rows can
still type-check.

Representative rows:

```semanticscript
taskGroup NAME maxTasks LIMIT cancelOnFirstError yes
startInGroup CALL GROUP
awaitGroup GROUP
bindGroupError NAME TYPE GROUP
workerPool NAME
work WORK_NAME TARGET
workArg WORK_NAME ARG VALUE
submitWork WORK_NAME POOL
awaitWork WORK_NAME
send CHANNEL VALUE
receive NAME TYPE CHANNEL
lock MUTEX
unlock MUTEX
select NAME
selectCase NAME TOKEN BRANCH
runSelect NAME
branchSelected NAME BRANCH target LABEL
```

`docs/reference/syntax-inventory.md` is the source of truth for which of these rows are executable,
synchronous fallback, metadata-only, or reserved.

## Type Universe

Primitive lowered types include:

```text
I1 / Bool                                      i1
Int8 / Int16 / Int32 / Int64                          integers
Float32 / Float64                                     floats
ExitCode / Int32                       i32
String / String            i8*
OpaquePointer                          i8*
Void / Void                                  void source contract
```

C-aligned aliases such as `ByteCount`, `AddressOffset`, `Float64`,
`FileHandle`, and related libc-facing names resolve through the compiler's type
resolver. User-declared aliases resolve transitively before codegen.

Opaque PascalCase types used only as operation inputs, dependency handles, or
runtime handles are accepted for source context and static analysis. They cannot
be used as ordinary data operands unless the backend has a concrete lowering for
that target.

## Call Targets

Primitive targets include:

```text
console.writeLine
console.writeIntegerLine
console.writeInteger
console.writeFloatLine

math.addInt64 / subtractInt64 / multiplyInt64 / divideInt64 / moduloInt64
math.equalInt64 / notEqualInt64 / lessThanInt64 / lessThanOrEqualInt64
math.greaterThanInt64 / greaterThanOrEqualInt64
math.checkedMultiplyInt64

pointer.loadByte / pointer.storeByte / pointer.offset / pointer.difference
pointer.isNull

json.*
sqlite.*
http.*
gui.*
c.*
```

`c.*` targets are resolved through `SemanticScript/compiler/libc_registry.py`.
The registry is an implementation detail for low-level runtime/backend work;
app-facing code should prefer standard modules and domain-specific APIs.

Dotted external-module targets that have no local body may lower to explicit
zero-shaped stubs when the surrounding code needs to remain inspectable. This is
a documented runtime gap, not a real external implementation.

## Import Resolution

`import ALIAS MODULE_PATH` registers a module alias. Explicit symbol imports
copy exported operations, types, errors, capabilities, and constants into the
current program under local names. Build files can register modules through
regular `BuildPlan` records with `jsonBody`, or through the legacy closed-row
build-tape surface still used internally by compatibility lowering.

## Invariants

The AST and linter enforce or report:

1. One semantic action per row.
2. Old replaced row verbs are rejected instead of silently stored as metadata.
3. Header rows name their owning operation.
4. Every referenced label resolves.
5. Fallible calls have explicit success/value disposition, error binding, and
   error branch, or use `runChecked`.
6. `return ok` and `return error` match the declared `Result` payload types.
7. `return void` appears only on `Void`/`Void` outputs.
8. Strict executable mode rejects unknown lowercase verbs.
9. JSON bodies are valid strict JSON and match their storage target.
10. Module names are dotted namespaces and conflicting module declarations fail.

## LLVM Mapping

| AST row or object | Lowering |
|---|---|
| `operation main` | `define i32 @main()` for console entry |
| non-entry user operation | LLVM function with flattened supported parameters |
| `label` | basic block |
| `storage module immutable` | LLVM constant/global literal as needed |
| `storage module mutable` | internal LLVM global |
| `storage local mutable` | entry-block alloca plus load/store |
| `call` + `argument` + `run` | resolved LLVM call or runtime dispatch |
| `runChecked` | call, binds, conditional branch, fall-through block |
| `bind value` / `bind ok` | SSA result binding |
| `bind error` | recorded error value or result fallback |
| `ignore ...` | explicit disposition marker, no instruction |
| `branch if` | conditional branch to target or fall-through |
| `branch error` | conditional branch using recorded error condition |
| `jump` | unconditional branch |
| `return value` / `return ok` / `return error` | typed LLVM `ret` |
| `return void` | zero sentinel for current user-op ABI |
| `jsonBody JsonText` | canonical JSON byte constant |
| `jsonBody record` | compile-time record constant / flattened fields |
| `sql body SqlText` | preserved SQL byte constant with placeholder/statement metadata |
| `html body template` | escaped or raw string construction helpers |

## Linter And Diagnostics

The linter reads the same flat tape. It uses the source line and origin maps to
emit diagnostics that point at the row responsible for the gap. Important checks
include unresolved references, checked-call completeness, resource cleanup,
return contract mismatches, HTTP handler response guarantees, JSON cursor
invalidation, SQL constant requirements, and naming discipline.

The linter imports shared fallibility facts from
`SemanticScript/shared/call_contracts.py`, so compiler and linter call-channel
behavior stay aligned.
