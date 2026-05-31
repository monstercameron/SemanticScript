# SemanticScript — EAV-Steps v0.3

A complete proposal for SemanticScript refined syntax. It keeps the flat
semantic-tape model, but normalizes rows around entity/predicate/payload shape
so agents can grep, patch, and validate one grammar instead of special-casing
verb families.

This is a proposed next syntax, not the currently executable syntax until the
parser, linter, docs, tests, and editor move together. It is still bound by the
project contract: effects, failures, cleanup, memory, time, and authority remain
source data. Authority is not deleted from the contract — it is represented more
explicitly through the `uses`+`grants`+`effect` trio than through the v0.1
`authority` keyword row. This version adds: typed return arity, first-class
cleanup registration, universal metadata attachment, HTML hydration/binding,
full web-server handler ABIs, type/record/enum entities, mutable rebinding via
call output, and lexical rules. Worked examples are fully updated.

> **Prototype status (this repo).** A keystone front end now exists at
> `experiments/eav-syntax/semanticscript.py`: it lexes (§2), parses (§1/§5), and *lowers*
> canonical EAV into the existing v0.1 verb-led source the reference compiler
> already runs — a second front end, not a backend fork. Hello World (§18),
> an arithmetic program, and a control-flow loop run end to end (e.g.
> `python semanticscript.py run examples/hello_world.sem` → `hello world`). The parser
> enforces the §5 per-kind predicate table and accepts the full grammar (the
> 66-entity webServer demo `main.sem` parses). See `todos.md` for per-item
> status and the proving tests in `test_semanticscript.py`. The linter (§17/MD rules),
> stdlib (§3B), formatter (§22), editor (§29 #7), and webServer/wasm/sqlite/http
> lowering remain unbuilt.

### Adoption framing

EAV-Steps is the **canonical normalized representation** of SemanticScript
source — the form the formatter canonicalizes to, the form agents patch, and
the form the linter checks against. It is not yet the mandatory primary
authoring syntax.

Current/compact verb-led syntax remains acceptable at the source level. The
toolchain maps both surfaces to the same canonical EAV form:

```
sem fmt --surface current    # emit current verb-led form        (proposed; §24)
sem fmt --surface eav        # emit canonical EAV form            (proposed; §24)
sem lower --to eav           # normalize an entire codebase to EAV (proposed; §24)
sem codemod --to-eav OP      # incrementally convert one operation (proposed; §24)
```

These four surfaces are **proposed**, not yet implemented (§24). Today the
closest existing surface is `sem migrate-syntax`; `sem fmt` exists but does not
yet take `--surface`, and `sem lower`/`sem codemod` do not exist.

EAV becomes the mandatory authoring surface only after conversion metrics on a
real app show:
- row count does not exceed the adoption gate (§21)
- edit-locality improves or stays neutral
- agent friction logs confirm the structural wins outweigh the row cost

Until then: EAV is how tools think; current syntax is how humans write.

**Direction (v0.4).** The keyword surface narrows to a **minimal core** (§34):
domain contracts — web server, HTML, the build manifest, metadata, comparators —
become records, stdlib calls, and `.semsig` signatures rather than keywords, while
the `call`/`task`/`cleanup` split and the effect/capability boundary stay
first-class. Fewer keywords, same guarantees.

The semantic wins from v0.3 land regardless of surface syntax:
`defer ... onFailure`, `async start/join/poll/cancel/detach`, return-arity
linting, `at`-label semantics, double-brace HTML holes, `HtmlSafeUrl` typed
holes, `ifVariant` variant matching, and resource cleanup registration
discipline.

---

## 1. Core row model

Four row classes, exhaustive:

```
entity row:       <entity>    is          <kind>
fact row:         <entity>    <predicate> <payload...>
step row:         <operation> <stepPred>  <payload...>
labeled step row: <operation> at          <label> <stepPred> <payload...>
```

- Column 1 is always the subject.
- Column 2 is always the predicate (or `at` for labeled steps).
- Column 3+ is the payload.
- Every entity's first row must be its `is` row.
- The `at` predicate introduces a label. The label occupies column 3; the step
  predicate occupies column 4+. `at` is never used as a general-purpose
  predicate.
- No `.label` pseudo-predicate. Labels are not predicates and never appear in
  column 2.

---

## 2. Parse rules

Lines are whitespace-tokenized. Alignment padding is cosmetic and
formatter-enforced.

**Exception:** indentation is semantic inside island bodies. Indentation after a
`body <kind>` row is the island; the first column-1 token-bearing row ends it.

### Lexical rules

**Identifiers (internal).** `[a-zA-Z][a-zA-Z0-9]*` — camelCase. Must start
with a letter. No underscores, hyphens, or leading digits. This rule applies to
all internal entity names, variable names, and type names. Type names
conventionally start with an uppercase letter; operation, call, and variable
names with a lowercase letter.

**External paths.** Module paths (used in `imports`, `path`), call targets
(used in `invokes`), effect paths, and resource paths are dot-separated
identifier sequences: `IDENTIFIER ('.' IDENTIFIER)*`. Each segment follows the
internal identifier grammar. Dots in external paths are path separators, not
member access (see §3). External path tokens are not subject to the reserved
words restriction in the same column positions.

**Repository paths, versions, and digests (manifest positions only).** A
dependency **repository path** is a slash-separated sequence whose segments allow
dots and hyphens — `[A-Za-z0-9][A-Za-z0-9._-]*` joined by `/`
(`github.com/ss-lang/sqlite`). A **version** token is full semver with a leading
`v`: `v<major>.<minor>.<patch>` plus an optional `-<pre-release>` (`v2.1.0-rc.1`)
and an optional `+<build-metadata>` (`v2.1.0+build.5`). A **digest** is the bare
keyword `sha256` followed by 64
lowercase hex characters. These three token classes are valid **only** in
`build.sem`/`build.sem.lock` manifest positions (`require`/`replace`/`resolved`/
`effectSurface`, §28) and a module's `imports` path; a local filesystem path (as
in `replace`) is written as a quoted string (`"../sqlite"`). They may not be used
as entity, variable, or type names. These version tokens are for **dependency**
versions only; `languageVersion`/`toolchain` take a free-form quoted string
(`"1.0"`, `"sem1.0"`), not a `v`-prefixed version token.

**Integer literals.** `[0-9]+` decimal, `0x…` hex, or `0b…` binary (§33.1); a
single `_` between digits is an ignored separator (`1_000`, `0xFF_FF`); no octal.
A literal takes the type of its annotated position and is range-checked at compile
time (§33.6); an un-annotated literal defaults to `Int64`.

**Negative literals.** `-[0-9]+` and `-[0-9]+\.[0-9]+` are negative integer
and float literals, valid in `let` initializer positions and `arg` value
positions only. No whitespace is permitted between the `-` sign and the digits:
`-42` is valid; `- 42` is a parse error. They are not a unary minus operator
applied to an expression — SemanticScript has no expression syntax. For
runtime-computed negative values, use an arithmetic call.

**Float literals.** `[0-9]+\.[0-9]+` — decimal float. No leading-dot or
trailing-dot forms. Float literals default to type `Float64`. To obtain a
`Float32` value, use an explicit conversion call (`convert.toFloat32`). There
is no literal suffix to distinguish the two widths.

**Duration literals.** `[0-9]+` immediately followed by a time unit — `ns`,
`us`, `ms`, `s`, `m`, or `h` — with no intervening space (`50ms`, `30s`). Valid
only in duration-typed positions — which (retry/interval/timeout) are all
deferred to a future version (§27), so no v0.3 program contains one yet; the
class is reserved now for lexer stability. Lowers to the stdlib `Duration` alias
(also stdlib-deferred, §27). There is no float duration literal — compose with a
smaller unit (`1500ms`). See §30.1.2.

**Bool literals.** `true` and `false`. Both are reserved words.

**String literals.** `"..."`. Supported escapes: `\"` (quote), `\\`
(backslash), `\n` (newline), `\t` (tab), `\xNN` (one raw byte, exactly two hex
digits — the only way to author a non-ASCII byte in a bytewise-UTF-8 `String`,
§33.1). `\u{…}` codepoint escapes are deferred to i18n (§29 #22). No raw strings in v0.3.
`\r` is intentionally unsupported — targets use `\n` only; CRLF line endings
are a transport/ABI concern handled by the stdlib or runtime, not the source
language. `\0` is intentionally unsupported — SemanticScript strings are not
null-terminated; null-byte handling is a C ABI detail the runtime manages
transparently.

**Comments.** `#` introduces a comment. Two forms are valid:
- **Full-line comment**: `#` at column 1; the entire line is a comment.
- **Trailing comment**: `#` after all payload tokens on a non-empty row; the
  rest of the line is a comment.

A `#` token starts a comment only when it appears **outside a string literal**.
Inside a `"..."` string, `#` is a literal character and has no special meaning.
The scanner treats a `"` open-quote as entering string context and exits on the
closing `"` (with standard escape rules); no `#` scanning occurs while in
string context.

No block comments. The formatter preserves trailing comments in place; `sem fmt`
does not strip them.

### Allowed punctuation in source

```
"..."   string literals
#       full-line (col 1) or trailing after payload
.       external target paths and resource paths only
/ - _   repository-path separator/segment chars — manifest positions only (§28)
+       semver build-metadata separator — version tokens only (`v1.4.0+build.5`)
->      not used
=       not used — `let` rows are positional (§12); there is no assignment operator
```

### Reserved words

The following tokens are reserved and may not be used as entity names, variable
names, or type names:

**Literals:**
```
nil true false
```

**Core syntax:**
```
is at
```

**Step predicates and guards:**
```
do defer start join poll cancel detach branch return goto set
if ifFalse ifOut ifValue ifVariant ifError ifReady ifPending ifCanceled else onFailure
equals notEquals greaterThan lessThan bind
propagate logAndSuppress because
```

**Mutability and declaration tokens:**
```
immutable mutable yes no
```

**Entity kind names:**
```
project module capability error errorCase record enum alias
operation function call task cleanup storage htmlTemplate webServer
intrinsic platform operationType semsig
```

`operationType` (§33.9) is a typed operation-reference signature — a
function-pointer type, no closures.

**Structural predicate tokens:**
```
in out effect uses memory async let label
field variant repr for of
path imports exports
scope type mutability value body literalSource literalDigest
grants invokes arg async discards catch
purpose invariant note rationale risk example tag deprecated owner
target owns cleanedBy cleans trustConstraint
using mode forTarget forPlatform suppress
version generatedBy describes
```

`mode` is a project-level predicate (§30.1.1); `forTarget`/`forPlatform`
(§30.3.1) and `suppress` (§30.6.2) are declaration predicates added in §30.
Mode/target *values* (`capturedOutputReplay`, `console`, `webServer`, `wasm`) are
payload tokens, not reserved names. `forTarget`, `forPlatform`, and `suppress`
are **universal** declaration predicates — valid on any entity kind (like §6
metadata) — and in
canonical row order they sort after the entity's structural and metadata rows
(§22). Lint: a `forTarget` value must be a target declared by the project; a
`suppress` row needs a real diagnostic code and a `because` string (§30.6.2,
§17 #54).

`ifVariant` and `bind` are active canonical guards (§13): `branch ifVariant
VALUE VARIANT [bind PAYLOAD] goto LABEL` is the first-class way to inspect a
data-carrying `enum`/`error` value and bind its payload on the taken path.
`bind` appears only inside that guard. (Earlier drafts reserved these for a
future `match`; v0.3 makes them the canonical data-inspection mechanism — there
is no `match` block.)

**Manifest predicate tokens (build.sem, §28):**
```
languageVersion toolchain require replace allowEffect platform constant
configure nativeLibrary nativeHeader nativeLinkFlag
os arch targetRuntime output override
```

**Generated lock predicate tokens (build.sem.lock, §28):**
```
resolved toolchainResolved effectSurface
```

**Interop annotation tokens (roadmap, §30.4.2):**
```
export c
```

**Primitive type names:**
```
Int8 Int16 Int32 Int64
UInt8 UInt16 UInt32 UInt64
Float32 Float64
Bool String Void Byte
Result
```

Unknown predicate for a known subject-kind is a hard parse error.

**Reserved words bind only entity, variable, and type names.** `arg` slot
names, `record` field names, and `enum` variant names are payload labels, not
names in the reserved namespace, and are exempt — e.g. `openDb arg path String
databasePath` and `Config field type String` are legal even though `path` and
`type` are reserved predicates. Slot, field, and variant labels are still
checked for duplicates within their own call, record, or enum.

---

## 3. Names, references, and external targets

Internal entity references are bare whole-word names with no dots:

```sem
main uses stdoutWriter
writeHello in main
main do writeHello
```

External targets (`invokes`, `grants`, effect paths, resource paths) may use
dots. Dots in these positions are path separators, not member access:

```sem
writeHello invokes console.writeLine
openDb invokes sqlite.openDatabase
dbReader grants read database
main effect write console.stdout
```

The rule: dots are forbidden in references to internal entities; dots are
allowed in external-path values. A `call`/`task` `invokes` target is therefore
bare when it names an in-module user operation (`invokes addTwoValues`) and
dotted when it names an imported, compiler-derived, or stdlib target
(`invokes accounts.lookupAccount`, `Task.new`, `console.writeLine`). See §15.

---

## 4. Reserved literals and words

`nil` is the absent-slot literal for `Result` returns:

```sem
lookupTask return taskValue nil
lookupTask return nil lookupError
```

`nil` is not used for single-value returns or void returns.

`true` and `false` are the Bool literals. Both may appear as `let` initializers
and as call argument values:

```sem
main let debugEnabled immutable Bool false
runCheck arg enabled Bool true
```

`yes` and `no` are declaration tokens, not Bool literals. They appear only in
specific declaration predicate value positions:

```sem
main async no       # declaration token — not a Bool
main memory heap no # declaration token — not a Bool
```

`yes`/`no` may not appear in step rows, `let` initializers, or `arg` values.
Use `true`/`false` for all Bool values in executable positions.

All reserved words are listed in §2. None may appear as entity, variable, or
type names.

---

## 5. Predicate vocabulary

Structural predicates are specific to each entity kind. Universal metadata
predicates (§6) are available on every entity kind and listed separately.

| Subject kind | Structural declaration predicates | Step predicates |
|---|---|---|
| `project` | `is module target entry mode languageVersion toolchain require replace allowEffect platform constant configure nativeLibrary nativeHeader nativeLinkFlag` + `.sem.lock`-only `resolved toolchainResolved effectSurface` | — |
| `module` | `is path imports exports` | — |
| `capability` | `is grants` | — |
| `error` | `is typeTrust` | — |
| `errorCase` | `is of payload` | — |
| `record` | `is field typeTrust` | — |
| `enum` | `is variant repr typeTrust` | — |
| `alias` | `is for typeTrust` | — |
| `sharedState` | `is scope type mutability value guard owner` (WS2-083) | — |
| `region` | `is strategy scope capacity` (WS1-112) | — |
| `operation` | `is in out effect uses memory async label let body export trustConstraint errorBoundary optOut maxIterations` | `do defer start join poll cancel detach branch return goto set at readShared setShared allocateIn releaseRegion` |
| `call` | `is in invokes arg out catch discards owns cleanedBy effect borrows lifetime mayEscape takesOwnership limit timeout budget` | — |
| `task` | `is in invokes arg out catch discards owns cleanedBy effect borrows lifetime mayEscape takesOwnership limit timeout budget` | — |
| `cleanup` | `is in call onFailure because cleans` | — |
| `storage` | `is scope type mutability value body literalSource literalDigest` | — |
| `htmlTemplate` | `is body` | — |
| `webServer` | `is host port startup shutdown notFound methodNotAllowed route middleware optOut` | — |
| `platform` | `is os arch targetRuntime output override nativeLibrary nativeHeader nativeLinkFlag` (build.sem, §28.1) | — |
| `intrinsic` | `is target arg out catch async owns trustConstraint clientResponse borrows lifetime mayEscape` | — |
| `semsig` | `is version generatedBy describes` (.semsig header, §26) | — |
| `operationType` | `is in out` (typed operation-reference signature, §33.9) | — |

Unknown predicate for a subject-kind: hard parse error.

The `project` predicates `resolved`/`toolchainResolved`/`effectSurface` are valid
only in generated `.sem.lock` files (§28). `export` on an operation
(`OP export c <symbol>`, §30.4.2) and the universal `forTarget`/`forPlatform`/
`suppress` rows (§30) are declaration predicates that sort after the entity's
metadata (§22).

**One tolerated exception:** `async` on a `call` entity. It is not part of the
canonical `call` predicate set above, but the compact/legacy surface accepts
`call ... async yes` as a deprecated predicate whose only effect is to promote
the call to a `task` on `sem fmt` (§15.5). Canonical EAV rejects `async` on a
`call`; `sem lint --strict` reports it as "deprecated; use `is task`."

The `label` declaration predicate on `operation` is used for label metadata —
not a separate entity kind. See §6.

---

## 6. Universal metadata

Every entity may carry metadata rows. Metadata rows are non-executable,
order-independent, and have no effect on runtime behavior.

### Universal metadata predicates

```
purpose invariant note rationale risk example tag deprecated owner
```

Valid on any entity kind:

```sem
thing purpose   "Why this exists."
thing invariant "What must always remain true."
thing note      "Useful implementation or design note."
thing rationale "Why this shape was chosen over the alternatives."
thing risk      "Known failure mode or operational caution."
thing example   "Small example of intended use."
thing tag       publicApi
thing deprecated "Use newThing instead."
thing owner     moduleName
```

`owner` is documentation/maintenance ownership, not execution structure. For
call membership, use `in`. Do not use `owner` for runtime wiring.

`tag` takes a bare identifier. Multiple `tag` rows are allowed per entity.

`deprecated` payload must be a quoted string giving the replacement or reason.

`purpose` payload must be a quoted string. **At most one** `purpose` row per
entity (a duplicate is a hard error); whether it is *required* depends on the
entity's visibility tier (§6 tiers above), so for most entity kinds it is optional.

`invariant` payload must be a quoted string. Multiple `invariant` rows are
allowed on a single entity.

### Required metadata — tiered by visibility

Metadata requirements depend on whether an entity is public (exported or an
entry point) or private (module-internal only).

**Modules** — always public; `purpose` and `invariant` are required regardless
of export status.

**Operations** — tiered:

| Visibility | `purpose` | `invariant` |
|---|---|---|
| Exported or project `entry` | required (MD1011: error) | required (MD1012: error) |
| Module-private | recommended (MD1021: warning) | optional (MD1022: info) |
| Generated / `runtimeBinding` | optional (MD1031: off) | optional (MD1032: off) |

All other entity kinds treat all metadata as optional.

```sem
# error — exported operation missing purpose and invariant
taskWeb exports healthHandler

healthHandler is operation
healthHandler out Int32
# MD1011, MD1012 fire here

# valid — exported with required metadata
healthHandler is operation
healthHandler out Int32
healthHandler purpose "Return open task count as plain text"
healthHandler invariant "Responds with a status code on every path"

# valid — private helper with no metadata (warning-level only)
formatCount is operation
formatCount in value Int64
formatCount out String
```

The tiering prevents garbage invariants on trivial private helpers while
preserving the documentation contract for public API surface.

```sem
examplesHelloWorld is module
examplesHelloWorld path examples.helloWorld
examplesHelloWorld purpose "Contain the Hello World console entry operation"
examplesHelloWorld invariant "Exports main as the only project entry operation"
```

### Label metadata

Labels have no entity declarations and cannot carry universal metadata rows
directly. To document a label, use the `label` declaration predicate on the
owning operation:

```sem
main label failed purpose "Shared failure exit for all stdout write errors"
main label retry note "Retry is bounded by maxAttempts, checked at retryCheck"
```

Grammar: `<operation> label <labelName> <metaPredicate> <payload>`

Valid meta-predicates for labels: `purpose`, `note`, `rationale`, `risk`, `tag`.

`invariant`, `example`, `deprecated`, and `owner` are not valid on labels.
Label metadata is scoped to the owning operation; the same label name in two
operations has independent metadata.

### Metadata requirements by entity kind

| Entity kind | Required metadata | Optional metadata |
|---|---|---|
| `project` | none | `purpose`, `note`, `tag` |
| `module` | `purpose`, `invariant` | `rationale`, `risk`, `tag`, `deprecated` |
| `operation` | tiered by visibility (see above) | `rationale`, `risk`, `example`, `tag`, `deprecated` |
| `capability` | none | `purpose`, `invariant`, `risk`, `tag` |
| `call` | none | `purpose`, `rationale`, `risk`, `tag` |
| `error` | none | `purpose`, `invariant`, `tag` |
| `errorCase` | none | `purpose`, `risk`, `tag` |
| `record` | none | `purpose`, `invariant`, `tag` |
| `enum` | none | `purpose`, `invariant`, `tag` |
| `alias` | none | `purpose`, `tag` |
| `storage` | none | `purpose`, `invariant`, `risk`, `tag` |
| `webServer` | none | `purpose`, `invariant`, `risk`, `tag` |
| `htmlTemplate` | none | `purpose`, `invariant`, `risk`, `example` |
| `task` | none | `purpose`, `rationale`, `risk`, `tag` |
| `cleanup` | none (`because` is required by `logAndSuppress`, §15.6) | `purpose`, `note`, `tag` |
| `intrinsic` | none (stdlib signature metadata, §26) | `purpose`, `note`, `risk` |
| `platform` | none (build.sem, §28.1) | `purpose`, `note`, `tag` |

---

## 7. Project and module entities

```sem
HelloWorld is project
HelloWorld module examplesHelloWorld
HelloWorld target console
HelloWorld entry main
```

The `project` entity and all its rows — `module`, `target`, `entry`, `mode`, and
the manifest rows (`languageVersion`/`toolchain`/`require`/`replace`/
`allowEffect`/`platform`/`constant`, §28) — live in **`build.sem`**, not in
module source. A module `.sem` file never restates `entry`, and there is no
separate source-level entry row. The examples in this section are `build.sem`
content. (This resolves the §7/§28 entry-ownership question: `build.sem` owns it.)

**Multi-target entry.** A single-target project declares one unqualified
`PROJECT entry <entity>`. A multi-target project (more than one `PROJECT target`)
may repeat `PROJECT entry`, gating each named entry **entity** with a `forTarget`
row on that entity (§30.3.1) — the entity is an `operation` for `console`/`wasm`
and a `webServer` for the `webServer` target, so the gate sits on whichever entity
`entry` names. Exactly one entry must be enabled per built target, or it is a hard
error. An unqualified `entry` is the default for every target with no
target-specific entry.

`target` values: `console`, `webServer`, `wasm` — the **program model and entry
ABI** (§11). A `target` is distinct from a *runtime* and a *platform*: `target`
is what kind of program is built; a `platform`'s `targetRuntime` (`native` |
`wasm`) is the execution substrate; the `platform` (os/arch/runtime) is where it
runs. `target wasm` implies `targetRuntime wasm`; `console`/`webServer` targets
build on native platforms. There is no separate `runtime` predicate.

`windowsGui` is a reserved target token for future use. GUI entity kinds,
message-loop structure, and handler ABIs are not specified in v0.3. Using
`target windowsGui` produces a compile error until the GUI module is defined.

Modules declare their own imports, exports, and required metadata:

```sem
examplesHelloWorld is module
examplesHelloWorld path examples.helloWorld
examplesHelloWorld purpose "Contain the Hello World console entry operation"
examplesHelloWorld invariant "Exports main as the only project entry operation"

taskWeb is module
taskWeb path app.taskWeb
taskWeb imports sqlite standard.sqlite
taskWeb imports http standard.http
taskWeb exports healthHandler
taskWeb exports createTaskHandler
taskWeb purpose "Serve the task management web application"
taskWeb invariant "All database access goes through databaseAccess capability"
```

`imports <alias> <modulePath>` — one row per imported module. The alias becomes
the namespace prefix for external target paths.

`exports <entity>` — one row per exported entity. All module entities default
to module-private. `exports` applies uniformly to any entity kind (`operation`,
`record`, `enum`, `alias`, `capability`, `error`, etc.).

**`entry` semantics by target.** The `entry` predicate on a project names the
root entity for that target:

| Target | `entry` names | Kind |
|---|---|---|
| `console` | the main operation | `operation` |
| `wasm` | the exported operation | `operation` |
| `webServer` | the server entity | `webServer` |

**Canonical EAV requires an explicit `exports` row for the entry entity.**
There is no implicit export in canonical EAV — visibility must always be
declared:

```sem
HelloWorld entry main
examplesHelloWorld exports main     # required in canonical EAV

TaskApp entry appServer
taskWeb exports appServer           # required in canonical EAV
```

Compact syntax may omit the exports row; `sem fmt` inserts it. The implicit
entry-is-exported rule is compact sugar only.

**Import namespace isolation.** Imported modules are accessed only via their
alias in external path positions (`invokes`, `grants`, effect paths, resource
paths). Imported names are never brought into the local entity namespace. Name
collisions between imports are therefore impossible — two modules may both
export `openDatabase` without conflict, since each is always accessed through
its alias prefix (e.g., `sqlite.openDatabase` vs `postgres.openDatabase`).

**Import type-name disambiguation.** Type names from imported modules are
referenced by bare name in `arg`, `out`, `catch`, `let`, and `field` type
positions. If two imported modules both export a type with the same bare name,
the linter reports an ambiguous type name.

To resolve, declare a local `alias` entity. In `alias for` rows only, the
target type may be qualified as `<importAlias>.<typeName>` to break the
ambiguity — this is the one position where a dotted type path is valid (§3):

```sem
# error — both standard.http and company.api export 'RequestError'
taskWeb imports http standard.http
taskWeb imports api company.api
# using bare RequestError anywhere is ambiguous

# fix — declare one local alias per imported type you use; qualify the target
# in the alias `for` row with the import-alias prefix
ApiRequestError is alias
ApiRequestError for api.RequestError     # api is the alias from imports api company.api
ApiRequestError purpose "Name company.api's RequestError locally"
HttpRequestError is alias
HttpRequestError for http.RequestError   # http is the alias from imports http standard.http
HttpRequestError purpose "Name standard.http's RequestError locally"
# reference ApiRequestError / HttpRequestError; bare RequestError stays a hard error
```

`<importAlias>.<typeName>` in a `for` row is a controlled exception to the
no-internal-dots rule. The prefix is the import alias — the same token as in
`imports api company.api` — not the module path. This makes it unambiguous:
`api.RequestError` means "the type named `RequestError` exported by the module
imported under the alias `api`." Dots in `for` targets are import-alias
qualifiers, not member access. Outside `for` rows, type names remain bare.

Declaring an alias does **not** silently hide the other import's type: a bare
ambiguous type name stays a hard error (there is no "first import wins" rule).
To reference either side you must name its local alias, so every use is
explicit. If declaring aliases for both is not worth it, prefer importing only
one of the conflicting modules.

**No re-exports.** A module may only export entities it declares itself. There
is no re-export syntax in v0.3 — to expose an imported module's entities,
declare a wrapper operation or type in the exporting module.

**Conversion from v0.1:**

| v0.1 | v0.3 |
|---|---|
| `buildProject X` + `project X` | `X is project` |
| `modulePath PROJ X` | `PROJ module X` |
| `target PROJ X` | `PROJ target X` |
| `targetRuntime PROJ native` | `PROJ target console` or drop if redundant |
| `targetRuntime PROJ webServer` | `PROJ target webServer` |
| `targetRuntime PROJ wasm` | `PROJ target wasm` |
| `mainOperation PROJ OP` | `PROJ entry OP` |
| *(no module entity in v0.1)* | Add `<mod> is module` + `<mod> path <path>` + required metadata |

---

## 8. Capability entity

The v0.1 `authority OP act res` rows are superseded by the `uses`+`grants`+
`effect` trio. The authority contract — who may perform which effects on which
resources — is preserved; only the keyword row is replaced.

```sem
stdoutWriter is capability
stdoutWriter grants write console.stdout
stdoutWriter purpose "Allow controlled writes to standard output"
stdoutWriter invariant "Only grants write access to console.stdout"

dbReader is capability
dbReader grants read database
```

Multiple grants: one `grants` row per action/resource pair.

Operation declares effects and the capability covering them:

```sem
main effect write console.stdout
main uses stdoutWriter
```

Lint: every `effect` must be covered by a `uses` capability whose `grants`
matches action + resource. Uncovered effect is a lint warning requesting a
covering capability.

**Threat model.** The capability/effect/trust-boundary system defends three
assets: *authority* — no operation performs an effect it did not declare and was
not granted, including through a primitive body (§11); *trust* — untrusted input
cannot reach a trust-sensitive sink without an explicit boundary (§16, §26); and
*supply chain* — a dependency's full effect surface is declared data the resolver
vets at link time (§28.5). The enforcement *algorithm* across the call graph is
gap #10 (§29); this is the asset/adversary statement that algorithm must satisfy.

**Conversion from v0.1:**

| v0.1 | v0.3 |
|---|---|
| `capability NAME` | `NAME is capability` |
| `resource NAME res` + `action NAME act` | `NAME grants act res` |
| `useCapability OP CAP` | `OP uses CAP` |
| `authority OP act res` | deleted; covered by `OP uses CAP` + `CAP grants act res` |

---

## 9. Error and error-case entities

All error cases are promoted entities. No inline `case` rows. This makes
enumeration a single grep per parent error.

```sem
ConsoleWriteError is error

ConsoleWriteFailed is errorCase
ConsoleWriteFailed of ConsoleWriteError
ConsoleWriteFailed payload Int32

ConsoleWriteClosed is errorCase
ConsoleWriteClosed of ConsoleWriteError
ConsoleWriteClosed payload Void
```

To enumerate all cases: `grep " of ConsoleWriteError"`.
To find a specific case: `grep "^ConsoleWriteFailed\b"`.

`payload` is optional. An error case with no payload carries no data.

**Conversion from v0.1:**

| v0.1 | v0.3 |
|---|---|
| `error NAME` | `NAME is error` |
| `errorCase NAME CASE TYPE` | `CASE is errorCase` + `CASE of NAME` + `CASE payload TYPE` |
| `errorCase NAME CASE` (no type) | `CASE is errorCase` + `CASE of NAME` |
| `ConsoleWriteError.ConsoleWriteFailed` reference | bare `ConsoleWriteFailed` |

---

## 10. Type, record, and enum entities

### Type entities are schema declarations

`record`, `enum`, and `alias` entities are type declarations only. They have
no step sequences and cannot be invoked or executed. They declare structure that
calls reference in `arg`, `out`, `catch`, and `let` type positions.

**Construction.** Record, enum, and error values are produced by typed call
outputs — there is no inline constructor syntax. Each declared type provides
compiler-derived construction and access targets that user code reaches with an
ordinary `call` (`<Record>.new`, `<Record>.<field>`, `<Enum>.<variant>`,
`<Error>.<case>`); see §10.5.

**Field access.** Record fields are read through the built-in `<Record>.<field>`
access targets (§10.5) or through template hydration (§16). There is no
dot-access notation on internal bindings.

**Mutation.** Record fields are not individually mutable. To update a record,
call `<Record>.new` (or a function that returns a new record value) and rebind
the existing `let mutable` binding via `out` (§12).

These constraints keep the execution model flat: all computation happens in
call steps; type declarations are pure schema.

### Primitive types

These types are built-in and require no `is` rows:

```
Int8 Int16 Int32 Int64
UInt8 UInt16 UInt32 UInt64
Float32 Float64
Bool String Void Byte
```

`UInt*` variants are unsigned integers of the same widths. Use `UInt8` for
raw byte values when sign-extension matters at C ABI boundaries. `Byte` is a
built-in **primitive synonym** for `UInt8` — *not* an `alias` entity, so the
alias strictness below (distinct, non-coercing) does not apply: the two name the
same primitive, are the same width, and are freely interchangeable at the ABI.
`Byte` is the conventional spelling in byte-buffer and I/O contexts.

All other named types are either declared as `record`, `enum`, or `alias`
entities in the same module, or come from an imported standard library module.
Types from standard modules are accessed via the module alias prefix in call
`invokes` and `arg` type declarations, but the type names themselves appear
bare in the source. Examples by module:

| Standard module | Example types |
|---|---|
| `standard.http` | `HttpRequest`, `HttpResponse`, `HttpTextBody`, `HttpStatusCode`, `HttpContentType`, `NextMiddleware`, `ServerContext` |
| `standard.sqlite` | `SqliteDatabase`, `SqliteStatement`, `SqliteStepResult`, `SqlText`, `SqliteOpenMode`, `SqliteQueryFailure`, `SqliteDatabaseOpenFailure`, `SqliteDatabaseCloseFailure` |
| `standard.html` | `HtmlTemplate`, `HtmlFragment`, `HtmlSafeUrl`, `HtmlTrustedFragment` |
| `standard.convert` | `ConversionError` |
| `standard.build` | `BuildPlan`, `BuildTarget` — **new in v0.3 (proposed module)** |
| `standard.test` | `TestResult` (+ `test.and`) — **new in v0.3 (proposed module)** |
| `standard.assert` | assertion targets `assert.*`; no exported types (maps to the repo's existing `standard.assert` if present) |

A module must import a stdlib module before using its types. If a type appears
in a `let`, `arg`, `out`, or `catch` row but its declaring module is not listed
in the module's `imports` rows, the linter reports an unknown type.

`ExitCode` (an `alias for Int32`) is a conventional process-exit type used by
console entry operations and by webServer startup/shutdown handler ABIs (§14).
It is not a primitive: declare it per module with `ExitCode is alias` +
`ExitCode for Int32`, as the Hello World example does (§18).

### Records

```sem
Task is record
Task field id Int64
Task field title String
Task field status TaskStatus
Task field createdAt Int64
Task purpose "Represent a single work item"
```

`field` rows: `NAME field FIELDNAME TYPE`. Document order is field declaration
order. Field names follow identifier grammar. Duplicate field names within one
record are a hard error.

Accessing a record's fields is done through typed calls or template hydration
(§16). No dot notation on internal entity references.

### Enums

```sem
TaskStatus is enum
TaskStatus variant open
TaskStatus variant inProgress
TaskStatus variant done
TaskStatus purpose "Represent the lifecycle state of a task"

SqliteOpenMode is enum
SqliteOpenMode variant readOnly
SqliteOpenMode variant readWrite
SqliteOpenMode variant readWriteCreate
```

`variant` rows: `NAME variant VARIANTNAME [PAYLOADTYPE]`. Variant names follow
identifier grammar. An optional payload type makes the variant a data carrier:

```sem
NetworkError is enum
NetworkError variant timeout Int32
NetworkError variant refused Void
NetworkError variant unreachable String
```

Payloadless variants carry no data. Duplicate variant names within one enum are
a hard error.

**ABI representation.** By default the compiler assigns integer discriminants
starting at 0 in declaration order. To declare explicit values for ABI
compatibility (e.g., POSIX flags, OS constants), use `repr` rows:

```sem
SqliteOpenMode is enum
SqliteOpenMode variant readOnly
SqliteOpenMode variant readWrite
SqliteOpenMode variant readWriteCreate
SqliteOpenMode repr readOnly 1
SqliteOpenMode repr readWrite 2
SqliteOpenMode repr readWriteCreate 6
```

`repr` row grammar: `NAME repr VARIANTNAME INTEGER`. All variants or no
variants in an enum must have `repr` rows — mixing explicit and auto-assigned
discriminants is a hard lint error. `repr` is only valid on payloadless
variants; data-carrying variants (with a payload type) do not use `repr`.

**Variant references.** Enum variants are only valid as values in
**type-directed positions** — positions where the expected type is statically
known to be a specific enum. The valid type-directed positions are: `arg` value
slots, `let` initializers, and `return` values. Using a bare variant name
outside a type-directed position is a hard parse error.

In a type-directed position, the declared type of the slot determines which
enum is searched:

```sem
openDb arg mode SqliteOpenMode readWriteCreate
```

The type `SqliteOpenMode` is in scope from the arg declaration; `readWriteCreate`
is looked up as a variant of that enum. The v0.1 fully-qualified style
(`readWriteCreateSqliteOpenMode`) is obsolete — drop the enum suffix.

### Aliases

```sem
ExitCode is alias
ExitCode for Int32

HttpStatusCode is alias
HttpStatusCode for Int32
```

`for` row: `NAME for TYPE`. The alias is a distinct named type that the type
checker does not silently coerce to its underlying type. Passing `Int32` where
`ExitCode` is required is a type error. An alias may target a primitive type or
another declared type.

The `TYPE` in a `for` row may be qualified as `<importAlias>.<typeName>` when
two imports share a bare type name and disambiguation is needed (see §7). This
is the only position in source where a dotted type reference is valid.

**Literal annotation.** Untyped literals (string `"..."`, integer `0`, float
`0.0`, bool `true`/`false`) carry no type until assigned. A literal used where
an alias is expected is annotated to that alias type — not coerced — because
the literal has no competing type to conflict with:

```sem
healthHandler let errorBody immutable HttpTextBody "Internal Server Error"
healthHandler let failStatus immutable HttpStatusCode 500
```

Both are valid.

**Explicit-annotation boundaries.** Both `arg` rows and `let` rows that write a
type explicitly are annotation boundaries. When the row declares an alias type
and the supplied binding has the alias's base type, the written type performs
the annotation — the programmer wrote the alias type at that position, so it is
visible and linter-checkable, not silent coercion:

```sem
formatCount out countText String                                # countText is String
writeOk arg body HttpTextBody countText                         # annotation at arg boundary
healthHandler let countBody immutable HttpTextBody countText    # same: annotation at let boundary
```

The two boundaries behave the same on purpose — accepting the annotation at
`arg` but rejecting it at `let` was a surprising asymmetry. What is *not* a
boundary is a position with no explicitly written type (for example a bare
`return countText` whose operation `out` is an alias): there the types must
already match.

The rule: literals annotate to any alias whose base type matches the literal
kind (no type competition). A named binding annotates to an alias wherever the
target type is written explicitly — `arg` slots and typed `let` rows. Positions
with no written type require an exact type match or an intermediate
alias-wrapping call.

### 10.5. Value construction and access

Compound values (records, enums, error cases) are never written as inline
literals. Each declared type provides compiler-derived **targets** that user
code reaches with an ordinary `call` (§15), so construction and access reuse the
call machinery rather than adding syntax. These targets are built in (like
`compare.*`): they need no `imports` row and are derived from the type's own
declaration in the same module.

**Construct a record** — `<Record>.new`. One `arg` per field, by field name;
`out` is the record:

```sem
buildTask is call
buildTask in createTaskHandler
buildTask invokes Task.new
buildTask arg id Int64 newTaskId
buildTask arg title String validatedTitle
buildTask arg status TaskStatus openStatus
buildTask arg createdAt Int64 nowSeconds
buildTask out task Task
```

All fields must be supplied; arg names and types must match the record's `field`
rows exactly. A record may not declare a field named `new` (the constructor
target reserves that segment).

**Read a record field** — `<Record>.<field>`. The `arg` is the record; `out` is
the field value:

```sem
readTitle is call
readTitle in renderTaskHandler
readTitle invokes Task.title
readTitle arg record Task task
readTitle out title String
```

**Construct an enum variant** — `<Enum>.<variant>`. A payloadless variant takes
no `arg`; a data-carrying variant takes its payload as the sole `arg`; `out` is
the enum:

```sem
openStatusValue is call
openStatusValue in createTaskHandler
openStatusValue invokes TaskStatus.open        # payloadless
openStatusValue out openStatus TaskStatus

timeoutValue is call
timeoutValue in retryHandler
timeoutValue invokes NetworkError.timeout       # data-carrying
timeoutValue arg value Int32 elapsedMs
timeoutValue out err NetworkError
```

**Discriminate an enum** — there is no `match`. Branch on a payloadless enum with
the `equals`/`notEquals` comparators, which accept enum operands (§13):

```sem
listHandler branch ifValue status notEquals openStatus goto skipRow
```

**Construct an error case** — `<Error>.<case>`. The payload (if the case declares
one) is the sole `arg`; `out` is the error. This replaces v0.1 `makeError`:

```sem
makeWriteFailure is call
makeWriteFailure in main
makeWriteFailure invokes ConsoleWriteError.ConsoleWriteFailed
makeWriteFailure arg status Int32 platformCode
makeWriteFailure out writeError ConsoleWriteError
main return nil writeError
```

**Inspecting data-carrying values.** Reading the payload *out* of a data-carrying
enum variant or an error case is done with the `branch ifVariant VALUE VARIANT
bind PAYLOAD goto LABEL` guard (§13): it narrows the value to a known variant and
binds its payload on the taken path (catch-style scope). A series of `ifVariant`
rows over one value is the match; exhaustiveness is linted. Records are read via
`<Record>.<field>`; payloadless enums are discriminated with `equals`/`notEquals`
(§13) or matched with `ifVariant`. There is no separate `match` *block* — variant
inspection reuses `branch`/`goto`, consistent with the flat tape.

### 10.6. Value semantics (numeric, equality, lifetime)

The type rows fix shape; this fixes the runtime contract authors may rely on.

**Numeric.** Signed and unsigned integers wrap on overflow (two's complement);
for overflow-sensitive arithmetic use the checked `math.*` operations, which
return a `Result`. Integer divide-by-zero and modulo-by-zero are a trap (the
process faults), never silent or undefined. `Float32`/`Float64` follow IEEE-754
(NaN, ±infinity, signed zero). Width changes and int↔float conversions are
explicit `convert.*` calls and may be fallible; there is no implicit numeric
coercion.

**Equality and ordering.** `equals`/`notEquals` (§13) are value comparisons:
integers and `Bool` compare by value; `Float` compares per IEEE-754, so
`NaN notEquals NaN` is true and `NaN equals NaN` is false; `String` compares
bytewise over its UTF-8 bytes (no Unicode normalization in v0.3); an `enum`
compares its variant. Ordering (`greaterThan`/`lessThan`) is numeric only —
`String`, `Bool`, and `enum` operands are rejected (§13, §17 #45).

**Evaluation order.** A call's `arg` rows are evaluated in document order; a
row's side effects occur at its activation step (`do`/`start`/`defer`), not at
the point its `call`/`task`/`cleanup` entity is declared. Declaration rows have
no evaluation order among themselves.

**Value lifetime (source contract; backend mechanism deferred).** Ordinary
values — primitives, `String`, and constructed `record`/`enum`/`error` values —
are **compiler-managed**: there is no user-visible allocator, no `free`, and no
GC pause in the source model. Their lifetime is handled by lowering (returned
values are copied or moved out of the operation), so `memory heap no` stays
satisfiable for operations that only build and pass ordinary values. Only
**external resources** — database/file/socket handles and raw heap — are
author-tracked, via `owns`/`cleanedBy` (§15) and `memory heap yes`. The source
contract is therefore: *never free an ordinary value; always release every
`owns`-tracked resource.* The exact managed-value strategy (region, arena, or
reference counting) is a backend choice deferred to §29 (gap #14) and does not
change this source contract.

---

## 11. Operation declaration rows

Metadata requirements on operations are tiered by visibility — exported and
entry operations require both `purpose` and `invariant`; private operations
produce a warning without them; generated or `runtimeBinding` operations are
exempt. See §6 for the full tier table.

```sem
main is operation
main out ExitCode
main effect write console.stdout
main uses stdoutWriter
main memory heap no
main async no
main purpose "Write hello world and return a process exit code"
main invariant "All stdout writes go through stdoutWriter"
main invariant "Returns writeFailedExitCode on any write failure"
```

For Go-style result/error output:

```sem
lookupTask out Result Task LookupError
```

`out Result <okType> <errType>` declares a two-value return. `out <type>`
declares a single-value return. Omit `out` for void operations.

`function` is accepted as an alias for `operation`. The formatter normalizes
`NAME is function` to `NAME is operation` at parse time. Legacy `function NAME`
syntax from v0.1 is not accepted. Because it normalizes away before checking,
`function` has **no** separate predicate set or metadata-table row — it shares
`operation`'s entirely (§5, §6).

**Memory policy vocabulary.** Multiple `memory` rows are allowed, one per
dimension:

```
<operation> memory heap yes|no
<operation> memory stack <bytes>
<operation> memory max <bytes>
```

`heap yes|no` — whether the operation may allocate on the heap. `stack N` —
maximum stack depth in bytes. `max N` — combined memory budget in bytes.
Integer byte values use the negative-free literal grammar (`[0-9]+`). Omitting
a dimension means the runtime default applies.

**`async` predicate — only valid on `operation` and `intrinsic`.** In canonical
EAV, `async` is not valid on `call` entities. Use a `task` entity for async
invocations:

| Subject kind | `async no` | `async yes` |
|---|---|---|
| `operation` | The operation itself does not suspend or run on a concurrent scheduler. A `start` step inside an `async no` operation is a hard error. | The operation may suspend or be scheduled asynchronously by the runtime. |
| `intrinsic` | (not used) | The intrinsic must be activated with `start`/`join`; using `do` on an async intrinsic is a hard error. |
| `call` | (compact sugar only — lowers to `call` entity without change; use `task` instead) | Deprecated compact sugar — `sem fmt` promotes this call to a `task` entity. |

For operations, `async` describes the operation's own scheduling contract. For
intrinsics, `async` describes the required activation discipline for callers.
For `call` entities, `async yes` is deprecated sugar; canonical EAV uses `task`
entities.

All declaration rows are order-independent. The one exception: multiple `in`
rows preserve parameter order by document order.

### Operation bodies

By default an operation's body is its step sequence. An operation may instead
declare a non-step body for interop, reusing the `body` predicate:

```
<operation> body steps                     # default; the operation has step rows
<operation> body runtimeBinding <target>   # body is a named runtime binding
<operation> body intrinsic <name>          # body is a compiler intrinsic
```

`body steps` is the default and is normally omitted. An operation with `body
runtimeBinding` or `body intrinsic` has **no** step rows; its `in`/`out`/`effect`
contract still applies and is what callers and the linter see. These bodies are
for the standard library and low-level runtime interop — application code rarely
needs them, and an unexported `runtimeBinding`/`intrinsic` operation is exempt
from the `purpose`/`invariant` requirement (§6). The compiler-derived
construction and access targets (§10.5) and the `compare.*` primitives (§13) are
provided this way and need no user declaration.

**Authority is not waived by dropping to a primitive.** Because the linter
cannot see inside a `runtimeBinding`/`intrinsic` body, the operation's declared
`effect` rows *are* the trusted contract: a non-step body must declare every
effect its binding performs, with `uses` covering them (§8) — the body cannot
legitimately perform an undeclared effect. A `body runtimeBinding`/`intrinsic`
row in an ordinary **application** module is a hard error ("primitive bodies belong in a
stdlib/`.semsig`-backed module, not app source", §17 #50): it is an unverifiable
authority assertion, so it is confined to the stdlib boundary where the `.semsig`
contract and effect surface are reviewed (§26, §28.5). This closes the path where
app code could otherwise bind a primitive to perform effects it never declared.

### Entry-point ABIs

The `entry` operation named by a project (§7) must match the target's ABI:

| Target | Entry signature |
|---|---|
| `console` | no `in` rows; `out ExitCode` (alias for `Int32`). Ambient input is reached through capability-gated targets, not parameters. |
| `wasm` | the exported operation's declared `in`/`out`; host communication beyond `in`/`out` is host-defined (§27). |
| `webServer` | the `entry` is the `webServer` entity, not an operation; its handler operations follow the §14 handler ABIs. |

A console `entry` that declares `in` parameters, or returns a type other than
`ExitCode`/`Int32`, is a hard error.

### Context and ambient inputs

Ambient resources — `console`, `environment`, `clock`, `process` — are **not**
threaded as `in` parameters or `arg` values. They are reached through
capability-gated stdlib targets (`console.writeLine`, `clock.nowSeconds`,
`environment.get`, …), each declared as an `effect` covered by a `uses`
capability (§8). The only values passed as `in`/`arg` are ordinary data and the
ABI-required handler bindings (`request`/`response`/`serverContext`/`next`, §14).
Do not add a `console`/`environment` parameter to a call: the target carries the
authority and the capability grants it.

**Conversion from v0.1:**

| v0.1 | v0.3 |
|---|---|
| `operation NAME` | `NAME is operation` |
| `input operation OP name TYPE` | `OP in name TYPE` |
| `output operation OP name TYPE` | `OP out TYPE` |
| `output operation OP Result OK ERR` | `OP out Result OK ERR` |
| `effect OP act path` | `OP effect act path` |
| `memory OP heap no` | `OP memory heap no` |
| `async OP no` | `OP async no` |
| `purpose operation OP "..."` | `OP purpose "..."` |
| `invariant operation OP "..."` | `OP invariant "..."` |

---

## 12. Local storage via `let`

Grammar:

```
<operation> let <name> <mutability> <type...> <value>
<operation> let <name> <mutability> <type...>
```

A `let` row is positional — there is no boundary symbol. Mutability comes first,
then the type, then an optional single initializer value. The type is parsed by
the type grammar (a primitive, alias, record, or enum name is one token; a
`Result OK ERR` type is three tokens), and any single token remaining after the
complete type is the initializer value. SemanticScript has no expression syntax
and no assignment operator: a `let` initializer is one literal or one in-scope
binding name, never a computed expression. There is no `=` anywhere in the
grammar.

```sem
main let helloText immutable String "hello world"
main let successExitCode immutable ExitCode 0
main let writeFailedExitCode immutable ExitCode 1
main let result mutable Result Int32 ConsoleWriteError
main let okStatus immutable HttpStatusCode 200
```

### Mutable rebinding via call output

When a call's `out` row names an existing `let mutable` binding of compatible
type, the call rebinds it — it does not declare a new binding:

```sem
sendWithRetry let attempt mutable Int32 0

incrementAttempt is call
incrementAttempt in sendWithRetry
incrementAttempt invokes math.addInt32
incrementAttempt arg left Int32 attempt
incrementAttempt arg right Int32 1
incrementAttempt out attempt Int32    # rebinds the mutable let above
```

Lint: `out` naming an `immutable` binding that already exists in scope is a
hard error. `out` naming a new name declares a fresh binding (immutable by
default unless the corresponding `let` declared it mutable).

`let` rows are declaration rows (order-independent within the operation).
Convention: place all `let` rows after `in`/`out`/`effect`/`uses`/`memory`/
`async`/`purpose`/`invariant` and before the first step row.

**Initializer forward-reference rule.** A `let` row with an initializer value
may only reference names that are already in scope at its point of declaration
by document order: `in` parameters (always in scope) or earlier `let` bindings
(those that appear before this row in document order within the operation). A
`let` row may not reference a `let` binding that appears later in the same
operation's declaration rows. Uninitialized `let mutable` rows (no initializer)
have no ordering constraint — they may appear in any order.

**Module-level storage** is a top-level entity, not a `let`:

```sem
schemaReady is storage
schemaReady scope module
schemaReady type Bool
schemaReady mutability mutable
schemaReady value false
```

**Single-line storage form.** Because a constant is one declaration, the
`is storage` row may carry the scope, mutability, type, and (optional) value
inline — `NAME is storage <scope> <mutability> <type> [value]` — consistent with
the one-line `let NAME <mutability> <type> <value>`. This is the compact
authoring form for module constants; it parses to the same scope/mutability/
type/value facts as the multi-row form above:

```sem
escapeByte is storage module immutable Int32 27
greeting is storage module immutable String "hello world"
lastRevision is storage module mutable Int64           # mutable, no initial value
```

### Mutating a mutable binding

A mutable binding — a local `let NAME mutable …` or a module-level `storage`
entity declared `mutability mutable` — is reassigned in one of two ways:

**1. From a call result (out-rebind).** A call whose `out` names the binding
rebinds it to the call's result. This is the form to use when the new value is
*computed* by an operation:

```sem
setSchemaReady is call
setSchemaReady in startupHandler
setSchemaReady invokes db.setSchemaReady    # user-defined or stdlib operation returning Bool
setSchemaReady arg db SqliteDatabase openedDb
setSchemaReady out schemaReady Bool         # rebinds the module storage entity
```

**2. From a literal/constant/binding (`set` step).** When the new value is a
literal, a constant, a parameter, or another in-scope binding — i.e. there is no
operation that *produces* it — use the `set` step:

```sem
counterOp set screenMode EditMode      # mutable local <- enum variant
counterOp set selectedIndex zeroValue  # mutable local <- another binding
startupHandler set schemaReady true    # module storage <- literal
```

`set NAME VALUE` assigns `VALUE` (a literal, a bare enum variant in the binding's
type, a constant, a parameter, or an in-scope binding) to the mutable binding
`NAME`. `set` is the imperative-assignment escape hatch the out-rebind form does
not cover; the out-rebind form remains preferred when the value comes from a
real call. Targeting an immutable `let` or immutable module storage — or an
unknown name — is a hard error (SS1087).

**Effect and capability requirement.** Mutation of module-level storage is a
visible side effect. The owning operation must declare an `effect` row covering
the mutation and a `uses` capability granting it. Storage effects use the
resource path `storage.<entityName>`:

```sem
schemaStateWriter is capability
schemaStateWriter grants write storage.schemaReady
schemaStateWriter purpose "Allow mutation of the schemaReady flag"

startupHandler effect write storage.schemaReady
startupHandler uses schemaStateWriter
```

This keeps module storage mutation visible in the effects model — it is not
silent global mutation sneaking in through an `out` row.

Lint: `out` targeting a module-level `storage` entity without a matching
`effect write storage.<name>` on the owning operation is a lint warning
requesting a covering capability. Targeting an `immutable` storage entity is a
hard error regardless of effects.

**Conversion from v0.1:**

| v0.1 | v0.3 |
|---|---|
| `storage local immutable NAME TYPE VAL` | `OP let NAME immutable TYPE VAL` |
| `storage local mutable NAME TYPE` | `OP let NAME mutable TYPE` |
| `storage module immutable NAME TYPE VAL` | `NAME is storage` + scope/type/mutability/value rows |
| `storage module mutable NAME TYPE` | same, `mutability mutable`, no `value` row |
| `set storage NAME VALUE` (value from a call) | call whose `out` targets the mutable entity |
| `set storage NAME VALUE` (literal/binding) | `OP set NAME VALUE` step |
| `set local NAME VALUE` | `OP set NAME VALUE` step |

---

## 13. Step sequence

An operation's step rows execute top to bottom in document order. Declaration
rows (including `let` and metadata rows) are unordered and do not participate
in execution order.

Step predicates: `do`, `defer`, `start`, `join`, `poll`, `cancel`, `detach`,
`branch`, `return`, `goto`, `set`, `at`. (`set NAME VALUE` assigns a mutable
local or module-storage binding from a literal/constant/binding — see §12.)

### `do` — invoke a synchronous call

```sem
main do writeHello
```

`do` accepts a `call` entity only. Using `do` on a `task` entity is a hard lint
error. Use `start` + `join` for async task invocations.

### `defer` — register a cleanup entity

```sem
healthHandler defer closeDbCleanup
```

Grammar:

```
<operation> defer <cleanupEntityName>
```

`defer` is a **registration step**: it schedules the named `cleanup` entity to
execute at every operation exit (before every `return`), in reverse registration
order. The cleanup does not execute at the point the `defer` row appears.

`defer` accepts a `cleanup` entity only. The old compound form
`OP defer CALL onFailure POLICY because "..."` is non-canonical sugar — the
formatter lowers it to a `cleanup` entity + canonical `defer` step.

**Cleanup policies.** Policy is declared on the cleanup entity (§15):

`onFailure propagate` — If the cleanup call fails, its error becomes the
operation's return error. Requirements: (1) the cleanup's call entity must
declare `catch`; (2) the owning operation must declare `out Result <ok> <err>`.

`onFailure logAndSuppress` — If the cleanup call fails, the runtime logs it
and preserves the in-flight return value. The `because` row on the cleanup
entity is required with this policy; omitting it is a hard lint error.

Runtime diagnostic logging from `logAndSuppress` is exempt from capability
tracking. Error chaining is not yet in scope.

Register a cleanup only after the value it consumes has been successfully
produced; for example, defer `closeDbCleanup` only after `openDb` has run and
`branch ifError openDb` has not jumped away.

### `branch` — conditional control transfer

```sem
main branch ifError writeHello goto failed
main branch if shouldRetry goto retry
main branch else goto failed
```

Grammar:

```
<operation> branch <guard> goto <label>
```

Canonical guards: `ifError <callName|taskName>` | `if <boolVar>` |
`ifFalse <boolVar>` | `ifVariant <value> <variant> [bind <payload>]` |
`ifReady <taskName>` | `ifPending <taskName>` | `ifCanceled <taskName>`

Non-canonical sugar guards (lowered by `sem fmt`, see "Non-canonical branch
sugar" below): `ifOut <callName> <comparator> <value>` |
`ifValue <varName> <comparator> <value>` | `else`

**`ifError` guard — predecessor rules.**

- For sync `call` entities: `branch ifError CALL goto LABEL` is valid after the
  nearest preceding `do CALL` in the same step sequence.
- For async `task` entities: `branch ifError TASK goto LABEL` is valid after
  `join TASK` in the same step sequence. `poll TASK` alone is not a valid
  predecessor; `poll` samples state but does not bind `out` or `catch` values.

`branch ifError` on a call with no `catch` row is a hard lint error regardless
of how the call was invoked.

At the target label, the catch variable declared by that call's `catch` row is
in scope.

The Go mapping:

```go
db, err := sqlite.OpenDatabase(dbPath, readWriteCreate)
if err != nil {
    goto failed
}
```

is exactly:

```sem
op do openDb
op branch ifError openDb goto failed
```

where `openDb` declares:

```sem
openDb out db SqliteDatabase
openDb catch openErr SqliteDatabaseOpenFailure
```

**`if` and `ifFalse` guards.** `branch if VAR goto LABEL` jumps when `VAR` is
true. `branch ifFalse VAR goto LABEL` jumps when `VAR` is false. Both require
`VAR` to be a `Bool` binding in scope at that step. Having both polarities
avoids negation calls — instead of computing `not hasRow`, use `branch ifFalse
hasRow goto loopDone`.

**`ifVariant` guard — variant matching and payload binding (canonical).** This is
the first-class way to inspect an `enum` or `error` value: test which variant it
is, and — if that variant carries a payload — bind the payload on the taken path.

```
OP branch ifVariant VALUE VARIANT goto LABEL                 # match a variant
OP branch ifVariant VALUE VARIANT bind PAYLOAD goto LABEL    # match and bind its payload
```

`VALUE` is an `enum` or `error` binding in scope; `VARIANT` is one of its
declared variants/cases, written bare and resolved type-directed (§10). `bind
PAYLOAD` is allowed only when that variant declares a payload, and `PAYLOAD` is
in scope **only on LABEL's path**, exactly like a `catch` variable at an
`ifError` target (§25). A payloadless variant omits `bind`.

```sem
# a caught error value, narrowed to a case, with its payload bound
classify branch ifVariant writeErr ConsoleWriteFailed bind platformStatus goto onWriteFailed
classify branch ifVariant writeErr ConsoleWriteClosed goto onClosed
classify at onWriteFailed do reportStatus   # platformStatus (Int32) is in scope here
```

A series of `ifVariant` rows over the same value *is* the match — one row per
variant, each routing to its arm. A variant-test series is a contiguous run of
`branch ifVariant` rows over the same `VALUE`, skipping comment and declaration
rows; it ends at the first step row that is not an `ifVariant` over that same
value. **Exhaustiveness is linted** over the series: if a closed `enum`/`error`
value is matched but not every variant is covered, the series must end in a
default transfer. The **canonical default is a plain `goto LABEL`**; `branch else`
is the non-canonical sugar for it and `sem fmt` lowers it to `goto`. Without full
coverage and no default, the linter warns (§17 #52).

**Payload definite-assignment.** When a label is the target of more than one
`ifVariant … bind` row, `PAYLOAD` is in scope there only if **every** branch
reaching the label binds the *same* payload name and type. If any predecessor
reaches it without binding `PAYLOAD` (or binds a different name/type), referencing
`PAYLOAD` at the label is a hard error — not definitely assigned (§17 #53) — the
same rule as a shared `catch` variable across failure labels (§25).

`ifVariant` is canonical (never lowered away); it is the v0.3 answer to
data-carrying inspection that earlier drafts deferred to a future `match`
(§10.5, §27).

#### Non-canonical branch sugar

`ifOut`, `ifValue`, and `else` are accepted in source but are **not** canonical
guards. `sem fmt` lowers each, so **canonical EAV never emits `ifOut`,
`ifValue`, or `else`** — it emits an explicit comparison call + `branch if`, or
a plain `goto`. They exist only to make hand-authoring terser; the canonical
guards above are the real control vocabulary.

**`ifOut` and `ifValue` guards.** Closed-vocabulary primitive comparisons that
eliminate separate comparison calls for simple status checks.

```
OP branch ifOut  CALL comparator VALUE goto LABEL
OP branch ifValue VAR  comparator VALUE goto LABEL
```

`ifOut CALL` requires `CALL` to have exactly one `out` binding (its sole
output) and compares that value; multi-output calls are not valid with `ifOut`.
`ifValue VAR` reads a named binding in scope.
`VALUE` is a literal or a binding name. Both forms are not expression syntax —
they test a single value against a single comparison with a fixed operator from
the closed vocabulary.

Comparators: `equals`, `notEquals`, `greaterThan`, `lessThan`

**Comparator lowering targets.** `ifOut`/`ifValue` lower to a call to a built-in
comparison primitive named `compare.<comparator><Type>`, where `<comparator>` is
the guard's comparator token and `<Type>` is the operand's primitive type name:

| Operand type | `equals` | `notEquals` | `greaterThan` | `lessThan` |
|---|---|---|---|---|
| `Int8`…`Int64`, `UInt8`…`UInt64` | ✓ | ✓ | ✓ | ✓ |
| `Float32`, `Float64` | ✓ | ✓ | ✓ | ✓ |
| `Bool` | ✓ | ✓ | — invalid | — invalid |
| `enum` (payloadless) | ✓ | ✓ | — invalid | — invalid |

`<T>` is the operand's type name, e.g. `compare.notEqualsInt32`,
`compare.greaterThanFloat64`, `compare.equalsBool`, `compare.equalsTaskStatus`.
**`Bool` and `enum` operands support only `equals`/`notEquals`** —
`greaterThan`/`lessThan` on them is a hard error (§17 #45). An enum comparison
tests the variant; the other operand must be a variant of the same enum in a
type-directed position (§10) or another binding of that enum type. This is how a
payloadless enum is discriminated, since v0.3 has no `match` (§10.5).
Float `equals`/`notEquals` follow IEEE-754 (§10.6): `NaN equals NaN` is false and
`NaN notEquals NaN` is true, so an `ifValue x equals x` guard does not always
hold for a `Float` operand. Data-carrying enums may not be compared (their
payloads make equality ambiguous); narrowing them is deferred (§27). The `compare.*` primitives are
built-in intrinsics and need no `imports` row (like `console.*` and `math.*`).
The comparison call's bool output feeds the `branch if` that replaces the sugar,
and its name follows the deterministic rule below (`check<Call>` / `<call>Check`).

```sem
healthHandler do writeOk
healthHandler branch ifOut writeOk notEquals successStatus goto writeFailed
healthHandler return writeResult
```

This replaces the previous three-row pattern (separate comparison call + status
check call + branch). The `successStatus` binding is a `let` value, keeping
the comparison free of magic literals:

```sem
healthHandler let successStatus immutable Int32 0
```

Lint: `ifOut CALL` requires the call to have exactly one `out` binding of a
comparable type — `Int8`–`Int64`, `UInt8`–`UInt64`, `Float32`/`Float64`, `Bool`,
or a payloadless `enum` — matching the comparator table above (including its
`Bool`/`enum` equals/notEquals-only restriction). Multi-output or `Void` calls
are not valid with `ifOut`. `ifValue VAR` requires `VAR` in scope and of such a
type. `VALUE` must match the type of the left-hand operand.

**`else` guard.** `branch else goto LABEL` fires unconditionally when reached.
Its runtime behavior is identical to `goto LABEL`. `branch else` is
non-canonical sugar: the formatter lowers it to `goto LABEL` in canonical EAV
output. It must appear after at least one `branch <guard>` row in the same
operation with no intervening step rows between it and its nearest preceding
guard branch. Only step rows break adjacency — declaration rows (`let`, `label`
metadata, `purpose`, `invariant`, etc.) and comment lines (`#`) do not. The
formatter warns to use `goto` instead if no preceding guard exists in the same
operation. `else` signals that this is the default path if none of the preceding
guards transferred control.

### `return` — terminate the operation

```
<operation> return
<operation> return <value>
<operation> return <okValue|nil> <errorValue|nil>
```

Return arity is determined by the operation's `out` row:

- No `out`, or `out Void`: `return`
- `out <type>`: `return <value>`
- `out Result <okType> <errType>`: `return <okValue|nil> <errorValue|nil>`

For `Result` returns, exactly one slot must be `nil`. Both-`nil` and
both-value returns are hard errors.

```sem
main return successExitCode
lookupTask return taskValue nil
lookupTask return nil lookupError
flushTelemetry return
```

### `goto` — unconditional transfer

```sem
main goto retry
```

### `at` — label definition

`at` is **one model, not two**: it is the step predicate that forms a *labeled
step row* (§1, row class 4) — `OP at LABEL <stepPred> <payload>` attaches `LABEL`
to the single step on that row (the `<stepPred>` in column 4 is an ordinary step
like `do`/`return`/`branch`). It appears in the operation step-predicate set (§5)
for exactly that reason; there is no separate label entity and no label-only row.

```sem
lookupTask at failed return nil lookupErr
main at retry do writeHello
```

If a label marks a multi-step block, only the first step carries the `at`:

```sem
main at failed do writeFail
main return writeFailedExitCode
```

Branch and goto references use bare label names:

```sem
main branch ifError writeHello goto failed
main goto retry
```

Lint: every `goto`/`branch ... goto LABEL` target must have exactly one
`OP at LABEL ...` row in the same operation.

### Control flow model — canonical primitive set

Step-target restrictions enforce one entity kind per activation verb:

| Verb | Accepted target kind | Rejected |
|---|---|---|
| `do` | `call` | `task`, `cleanup` |
| `start` `join` `poll` `cancel` `detach` | `task` | `call`, `cleanup` |
| `defer` | `cleanup` | `call`, `task` |

```
OP do CALL
OP defer CLEANUP
OP start TASK
OP join TASK
OP poll TASK
OP cancel TASK
OP detach TASK "reason"
OP branch ifError CALL goto LABEL
OP branch ifError TASK goto LABEL
OP branch ifVariant VALUE VARIANT goto LABEL
OP branch ifVariant VALUE VARIANT bind PAYLOAD goto LABEL
OP branch ifReady TASK goto LABEL
OP branch ifPending TASK goto LABEL
OP branch ifCanceled TASK goto LABEL
OP branch if BOOLVAR goto LABEL
OP branch ifFalse BOOLVAR goto LABEL
OP goto LABEL
OP return
OP return VALUE
OP return OKVALUE|nil ERRVALUE|nil
OP at LABEL STEP...
```

### Non-canonical accepted sugar

The following forms are accepted in source but are not part of the canonical
primitive set. The formatter lowers each to its canonical equivalent on
`sem fmt`:

| Accepted sugar | Canonical output | Notes |
|---|---|---|
| `OP branch else goto LABEL` | `OP goto LABEL` | intent comment only; no distinct semantics |
| `OP branch ifOut CALL cmp VALUE goto LABEL` | `OP do checkCmp` + `OP branch if result goto LABEL` | lowers to comparison call + bool branch |
| `OP branch ifValue VAR cmp VALUE goto LABEL` | `OP do checkCmp` + `OP branch if result goto LABEL` | same lowering |
| `call async yes` (entity fact) | `task` entity declaration | `sem fmt` promotes the call to a task entity |
| `OP defer CALL onFailure POLICY because "..."` | `CLEANUP is cleanup` entity + `OP defer CLEANUP` | compound form lowers to a named cleanup entity |

`branch else` signals author intent but conveys no distinct runtime semantics
beyond `goto`. `ifOut`/`ifValue` are comparison-then-branch expressed in one
row; canonical EAV makes the comparison call explicit so the result binding is
named and the lint surface is uniform.

**Deterministic generated names.** Lowering must produce stable names so a
second `sem fmt` is a no-op (no diff churn):
- `branch ifOut CALL cmp VALUE` → a comparison call `check<Call>` with a bool
  output `<call>Check` — e.g. `branch ifOut writeOk notEquals successStatus`
  generates `checkWriteOk` with `out writeOkCheck Bool`.
- `branch ifValue VAR cmp VALUE` → `check<Var>` with bool output `<var>Check`.
- compound `defer CALL ...` → cleanup entity `<call>Cleanup` (§15.6).
- **Reuse before generate:** if a comparison call with the same target and the
  same operands already exists in the operation, the formatter reuses it rather
  than emitting a new one, so a hand-written comparison call is never
  duplicated.
- **Collision:** if the chosen name is already taken by an entity of a
  *different* shape, append the lowest free numeric suffix (`checkWriteOk2`).

Reuse-before-generate plus the collision rule together make lowering
idempotent.

No `loop`, `while`, `each`, `break`, `continue`, or `end` predicates exist in
v0.3. All iteration and multi-exit patterns are expressed as labeled gotos.

**While loop** — condition tested at top:

```sem
scanRows at loopCheck branch ifFalse hasMoreRows goto loopDone
scanRows do readRow
scanRows branch ifError readRow goto scanFailed
scanRows do processRow
scanRows goto loopCheck

scanRows at loopDone return result nil
scanRows at scanFailed return nil readErr
```

**Retry loop** — bounded retry with counter:

```sem
sendWithRetry let attempt mutable Int32 0
sendWithRetry let maxAttempts immutable Int32 3

sendWithRetry at retryCheck do checkCanRetry
sendWithRetry branch ifFalse canRetry goto exhausted
sendWithRetry do sendRequest
sendWithRetry branch ifError sendRequest goto retryNext
sendWithRetry return response nil

sendWithRetry at retryNext do incrementAttempt
sendWithRetry goto retryCheck

sendWithRetry at exhausted return nil sendErr
```

**Conversion from v0.1:**

| v0.1 | v0.3 |
|---|---|
| `run CALL` | `OP do CALL` |
| `start CALL` | `OP start CALL` |
| `await CALL` | `OP join CALL` |
| `cancel CALL` | `OP cancel CALL` |
| `branch error source CALL target LABEL` | `OP branch ifError CALL goto LABEL` |
| `branch if condition VAR target LABEL` | `OP branch if VAR goto LABEL` |
| `branch else target LABEL` | `OP branch else goto LABEL` |
| `return value X` | `OP return X` for single-output operations |
| `return ok X` | `OP return X nil` for `Result` operations |
| `return error X` | `OP return nil X` |
| `return void` | `OP return` |
| `label NAME` (standalone) | `OP at NAME <nextStep...>` |
| `jump target LABEL` | `OP goto LABEL` |

### Async step primitives — `task` entities

Async follows the same goto philosophy: explicit task lifecycle steps, no hidden
scheduler semantics, no structured `async/await` blocks.

**`task` entity declaration.** Async invocations use a `task` entity, not a
`call` entity. `task` is the async counterpart to `call`:

```sem
fetchUser is task
fetchUser in main
fetchUser invokes http.getJson
fetchUser arg url String userUrl
fetchUser out user User
fetchUser catch fetchUserErr HttpError
```

`task` entities have no `async` predicate — being a task implies async. The old
`call async yes` form is deprecated compact sugar; `sem fmt` lowers it to a
`task` entity.

**`start TASK`.** Start the task lifecycle. `start` accepts a `task` entity
only. On a concurrent backend it may return before the task completes; on a
sync-fallback backend it dispatches directly.

**`join TASK`.** Suspend until `TASK` completes, then bind its `out` and `catch`
values. After `join`, the task's output bindings are in scope and `branch
ifError` is valid. `join` on an already-completed task returns immediately.

**`poll TASK`.** Sample the task's state without suspending. Binds no output
values. Use `branch ifReady`/`ifPending`/`ifCanceled` to route. To access
`out`/`catch` values after `poll` + `ifReady`, always follow with `join` at the
ready label; `poll` alone does not bind outputs.

**`cancel TASK`.** Request cancellation and consume ownership of the task.
Cancellation is cooperative and best-effort: the runtime signals the callee,
but the callee may complete normally before the signal arrives. The caller does
not wait for acknowledgement; `cancel` returns immediately. After `cancel`, the
operation is no longer responsible for the task and may return freely. `join`
after `cancel` binds the final `out`/`catch` values and allows `branch
ifCanceled` to distinguish a canceled task from one that completed before
cancellation took effect.

**`detach TASK "reason"`.** Release ownership of a started task without waiting.
Payload must be a quoted string explaining why the result is not consumed. Used
for fire-and-forget.

**Async branch guards:**
- `ifReady TASK` — true when the task has completed (success or failure)
- `ifPending TASK` — true while the task is still running
- `ifCanceled TASK` — true if the task was canceled before completing; valid
  only after `join TASK` following a `cancel TASK`

**Task lifecycle state table:**

| State | Entered by | Valid next steps | Valid guards | Illegal |
|---|---|---|---|---|
| RUNNING | `start TASK` | `poll`, `join`, `cancel`, `detach` | `ifPending`, `ifReady` (after poll) | `branch ifError` |
| COMPLETED | `poll`+`ifReady` landing | `join` (required before outputs) | — | `branch ifError` before `join` |
| CONSUMED | `join` | `branch ifError` | `ifError` | `ifPending`, `ifReady`, `ifCanceled` |
| CANCELED | `cancel` | `join` (optional) | — (until join) | any branch without join |
| CANCELED+JOINED | `join` after `cancel` | `branch ifCanceled` | `ifCanceled`, `ifError` | `ifPending`, `ifReady` |
| DETACHED | `detach` | — (ownership released) | — | any further step on this task |

Rules derived from the table:
- `branch ifError TASK` is only valid in the CONSUMED or CANCELED+JOINED state.
- `poll` may be called repeatedly without advancing state; it observes without
  consuming.
- `join` on a COMPLETED task (already done) returns immediately.
- `ifPending` after `join` is a hard lint error — task is already consumed.
- `ifReady` after `join` is a hard lint error — redundant; task is consumed.

**Fire-and-join (fan-out, possibly concurrent):**

```sem
main start fetchUser
main start fetchOrders

main join fetchUser
main branch ifError fetchUser goto userFailed

main join fetchOrders
main branch ifError fetchOrders goto ordersFailed

main do renderDashboard
main return dashboard nil

main at userFailed return nil fetchUserErr
main at ordersFailed return nil fetchOrdersErr
```

Where `fetchUser catch fetchUserErr HttpError` and `fetchOrders catch
fetchOrdersErr HttpError` declare separate error variables. Separate failure
labels prevent the wrong error variable from being in scope at the return site.

**Polling loop (cooperative scheduling):**

```sem
main start fetchUser

main at waitUser poll fetchUser
main branch ifPending fetchUser goto waitUser
main join fetchUser
main branch ifError fetchUser goto fetchFailed
main return user nil

main at fetchFailed return nil fetchUserErr
```

`join` at the exit of the polling loop binds `user` and `fetchUserErr` before
the `branch ifError` check.

**Timeout — modeled as a concurrent timer:**

```sem
main start fetchUser
main start timeoutTimer

main at waitAny poll fetchUser
main branch ifReady fetchUser goto userReady
main poll timeoutTimer
main branch ifReady timeoutTimer goto timedOut
main goto waitAny

main at userReady cancel timeoutTimer
main join fetchUser
main branch ifError fetchUser goto fetchFailed
main return user nil

main at timedOut cancel fetchUser
main return nil requestTimeoutErr

main at fetchFailed return nil fetchUserErr
```

At `userReady`, `cancel timeoutTimer` consumes ownership of the timer. Then
`join fetchUser` binds `user` and `fetchUserErr` for the error check. At
`timedOut`, `cancel fetchUser` consumes ownership of the fetch; `requestTimeoutErr`
is a `let` binding declared earlier on the operation.

**Race — first ready wins:**

```sem
main start primaryRequest
main start backupRequest

main at race poll primaryRequest
main branch ifReady primaryRequest goto primaryReady
main poll backupRequest
main branch ifReady backupRequest goto backupReady
main goto race

main at primaryReady cancel backupRequest
main join primaryRequest
main branch ifError primaryRequest goto primaryFailed
main return primaryResponse nil

main at backupReady cancel primaryRequest
main join backupRequest
main branch ifError backupRequest goto backupFailed
main return backupResponse nil

main at primaryFailed return nil primaryErr
main at backupFailed return nil backupErr
```

At each ready label, `cancel` the losing task (consuming its ownership), then
`join` the winning task to bind its output. Separate failure labels ensure each
error variable is in scope at its respective return site.

**Fire-and-forget — `detach`:**

```sem
main start sendMetric
main detach sendMetric "telemetry may complete after response"
```

**Backend semantics: concurrent vs sync-fallback.** The task lifecycle is a
contract, not a promise of parallelism. On a **concurrent** backend, `start` may
return before the task completes and `poll` can observe `ifPending`. On the
current **single-thread cooperative (sync-fallback)** backend, `start` dispatches
the task eagerly and runs it to completion, so by the time control returns the
task is already COMPLETED: `poll` always reports `ifReady`, `ifPending` is never
taken, and a poll/`goto` wait loop runs at most once. Race and timeout examples
therefore resolve deterministically to whichever task was `start`-ed first. The
source is identical on both backends — only the scheduler differs — so write to
the lifecycle contract and do not assume parallelism unless the target backend
provides it (true concurrency primitives are deferred, §27).

**Async lint rules (additions to §17):**
- `start TASK` requires `TASK` to be a `task` entity. Passing a `call` entity
  to `start` is a hard error.
- `do TASK` where `TASK` is a `task` entity is a hard error. Use `start`.
- `join TASK` and `poll TASK` require a preceding `start TASK` on every
  reachable path.
- `branch ifError TASK` after a task requires a preceding `join TASK`
  (not merely `poll TASK`) in the same step sequence.
- `branch ifReady`/`ifPending`/`ifCanceled TASK` requires a preceding `poll
  TASK` or `join TASK`.
- `branch ifCanceled TASK` requires a preceding `cancel TASK` followed by
  `join TASK`.
- `cancel TASK` requires the task to have been `start`-ed on the current path.
- Every started task must be `join`-ed, `cancel`-ed, or `detach`-ed before
  `return`. Unresolved started task at operation exit is a hard error.
- `detach TASK "reason"` payload must be a quoted string.

---

## 14. webServer entity

```sem
appServer is webServer
appServer host "127.0.0.1"
appServer port 8080
appServer startup startupHandler
appServer shutdown shutdownHandler
appServer notFound notFoundHandler
appServer methodNotAllowed methodNotAllowedHandler
appServer route GET "/health" healthHandler
appServer route POST "/tasks" createTaskHandler
appServer route GET "/" dashboardHandler
appServer middleware "/tasks" authMiddleware
```

Route document order is route-match priority. Identical routes (same method +
path) are a hard lint error.

**Dynamic routing.** A path segment of the form `:name` is a route parameter
(e.g. `route GET "/api/todos/:id" showTodoHandler`); `*` is the catch-all
wildcard used as the not-found fallback (`route GET "*" notFoundHandler`). The
`:name` segment must name a valid identifier. Document order is match priority,
so list static routes before the `*` catch-all. Parameter extraction and the
wildcard fallback are part of the webServer runtime and lower with the
`target webServer` codegen. Query-string binding is still out of scope (read
the query through `http.requestQueryParam`).

HTTP method values: `GET POST PUT DELETE PATCH HEAD OPTIONS`. Bare names, no
quotes.

### Handler ABIs

All handlers are operations. Their `in`/`out` declarations must match the ABI
for their role:

**Request handlers** (used in `route`, `notFound`, `methodNotAllowed`):

```sem
healthHandler is operation
healthHandler in request HttpRequest
healthHandler in response HttpResponse
healthHandler out Int32
healthHandler purpose "..."
healthHandler invariant "..."
```

**Request-handler `out Int32` semantics.** This is a completion code, not the
HTTP status: `0` means the handler finished and its response is finalized; a
non-zero value is a handler error the dispatcher logs (the handler must still
have written a response). The HTTP status sent to the client is set separately
through the response API — e.g. the `status` arg to `http.responseText` (`200`,
`500`). `http.responseText` returns `0` on success, so handlers typically return
its result directly (as §19 does).

**Startup and shutdown handlers**:

```sem
startupHandler is operation
startupHandler in serverContext ServerContext
startupHandler out ExitCode
startupHandler purpose "Initialize server resources before accepting requests"
startupHandler invariant "Returns 0 on success; non-zero halts server startup"

shutdownHandler is operation
shutdownHandler in serverContext ServerContext
shutdownHandler out ExitCode
shutdownHandler purpose "Release server resources after the last request"
shutdownHandler invariant "Returns 0 on clean shutdown; non-zero is logged"
```

**Middleware handlers** (used in `middleware`):

```sem
authMiddleware is operation
authMiddleware in request HttpRequest
authMiddleware in response HttpResponse
authMiddleware in next NextMiddleware
authMiddleware out Bool
authMiddleware purpose "Enforce authentication before passing to the next handler"
authMiddleware invariant "Returns false if auth fails; the route handler is not called"
```

`out Bool` return: `true` continues the middleware chain; `false` short-circuits
it. The middleware is responsible for writing any rejection response before
returning `false`. To pass control to the next middleware or handler, invoke
`http.callNext` with the `next NextMiddleware` binding as an arg:

```sem
invokeNext is call
invokeNext in authMiddleware
invokeNext invokes http.callNext
invokeNext arg next NextMiddleware next
invokeNext out continued Bool
```

Then `authMiddleware do invokeNext` in the step sequence. The `continued` output
is the return value of the downstream chain; the middleware returns it directly
or checks it before returning. Middleware rows on the webServer entity apply to
the path prefix in document order.

**Conversion from v0.1:**

| v0.1 | v0.3 |
|---|---|
| `webServer NAME` | `NAME is webServer` |
| `serverHost NAME X` | `NAME host X` |
| `serverPort NAME N` | `NAME port N` |
| `route NAME METHOD PATH HANDLER` | `NAME route METHOD PATH HANDLER` |
| `routeNotFound NAME H` | `NAME notFound H` |
| `routeMethodNotAllowed NAME H` | `NAME methodNotAllowed H` |
| `webServerStartup NAME H` | `NAME startup H` |
| `webServerShutdown NAME H` | `NAME shutdown H` |
| `routeMiddleware NAME PATH OP` | `NAME middleware PATH OP` |
| `staticRoute NAME PREFIX DIR` (static-file serving) | not in v0.3 — static-file serving is out of scope (§27); `route` is exact-match request routing, not file serving |
| startup/shutdown with no input (`out ExitCode`) | add `in serverContext ServerContext` as first arg |

---

## 15. Call entity

A call's only activation verb is `do`. `start` is for `task` entities; `defer`
is for `cleanup` entities (§15.5, §15.6).

`in` declares the owning operation. `invokes` is an external target path (dots
allowed, §3). `arg` rows: `<call> arg <slotName> <type> <value>` — document
order is argument order.

### Infallible calls — `out` only

```sem
rowAvailable is call
rowAvailable in healthHandler
rowAvailable invokes sqlite.stepResultIsRow
rowAvailable arg stepResult SqliteStepResult stepResult
rowAvailable out hasRow Bool
```

### Fallible calls — `out` + `catch`

```sem
openDb is call
openDb in healthHandler
openDb invokes sqlite.openDatabase
openDb arg path String databasePath
openDb arg mode SqliteOpenMode readWriteCreate
openDb out db SqliteDatabase
openDb catch openErr SqliteDatabaseOpenFailure
```

The operation executes it and immediately tests the error slot:

```sem
healthHandler do openDb
healthHandler branch ifError openDb goto failed
```

`branch ifError` is not magic exception flow. It is an explicit test against the
named call's catch variable.

### Ownership rows

`owns` declares that the call's `out` value carries a resource that requires
cleanup. `cleanedBy` names the cleanup entity responsible for that resource:

```sem
openDb is call
openDb in healthHandler
openDb invokes sqlite.openDatabase
openDb arg path String databasePath
openDb out db SqliteDatabase
openDb catch openErr SqliteDatabaseOpenFailure
openDb owns db                       # db is a resource requiring cleanup
openDb cleanedBy closeDbCleanup      # the closeDbCleanup ENTITY (§15.6) is responsible for db
```

`owns` without `cleanedBy` is a lint warning — the resource is acquired but no
cleanup is registered. `cleanedBy` without a matching `cleanup` entity declaration
is a hard error.

### Borrowed-view rows (WS1-111, §32.1 #9)

**Resources clean up; views do not.** A call/task whose `out` borrows another
resource/region — rather than acquiring its own — declares it with `borrows`,
names what it borrows from with `lifetime`, and states whether it may outlive the
call with `mayEscape`:

```sem
sliceRow is call
sliceRow invokes buffer.slice
sliceRow arg source Buffer buffer
sliceRow out window Slice
sliceRow borrows buffer               # a view into `buffer`, not a new resource
sliceRow lifetime buffer              # valid only while `buffer` is live
sliceRow mayEscape no                 # must not be returned past that lifetime
```

This is a lifetime/escape checker, not a borrow checker:

- A view (`borrows` present) may not also `owns`/`cleanedBy` — a view never
  cleans up (**SS1566**).
- A `mayEscape no` view may not be returned out of its operation; it would
  outlive its borrowed source (**SS1560**).

A *resource* without cleanup is already SS1503/SS3900 (above).

### Ownership transfer rows (WS1-113, §32.1 #9)

Passing an owned handle to a call **borrows** it by default — the caller keeps
ownership and its cleanup duty. Transfer is explicit, declared either as an `arg`
tail or a call-level row:

```sem
closeOver is call
closeOver invokes runtime.adopt
closeOver arg handle OpaquePointer fileHandle consumes yes   # transfer (move)
# — or, equivalently —
closeOver takesOwnership fileHandle
```

Once a handle is consumed (moved), reusing it — as a later call argument or a
`return` — is a use-after-move hard error (**SS1564**). `consumes no` (or no
tail) is a borrow and the handle stays caller-owned. The check is linear over the
operation's step order and stays conservative across labels.

### Guarded shared state (WS2-083, §8/§27)

Cross-task mutable state is a `sharedState` entity that names the guard token
protecting it; every access holds that token:

```sem
hitCount is sharedState
hitCount scope process            # process | module
hitCount type Int64
hitCount mutability mutable
hitCount value 0
hitCount guard hitCountLock        # the token that must be held to touch it

# inside an operation:
recordHit setShared hitCount nextValue protectedBy hitCountLock
recordHit readShared currentHits Int64 hitCount protectedBy hitCountLock
```

A `readShared`/`setShared` with no `protectedBy`, or one naming a token other than
the state's declared `guard`, is a hard error (**SS3083**); the `scope` must be
`process` or `module` (**SS3084**). On the single-thread backend the state lowers
to a global and the guard is a no-op (`setShared`→store, `readShared`→load), so it
JIT-runs; the guard contract is what a concurrent backend will enforce.

### Allocation regions (WS1-112, §29 #14)

A `region` is an allocation scope (`strategy arena|fixedBuffer|general`).
Objects are `allocateIn` it, and the whole region is freed at scope exit by one
`releaseRegion` — so an arena allocates many and frees once:

```sem
requestArena is region
requestArena strategy arena
requestArena scope handleRequest
arenaAllocCap is capability
arenaAllocCap grants allocate heap.requestArena   # allocator-as-capability

# inside the scoped op (which `uses arenaAllocCap`):
handleRequest allocateIn requestArena scratchA OpaquePointer
handleRequest allocateIn requestArena scratchB OpaquePointer
handleRequest releaseRegion requestArena           # frees both slabs, once
```

Allocating without a capability granting `allocate heap.<region>` is a hard error
(**SS1563**); an `allocateIn`/`releaseRegion` naming an undeclared region, or
releasing a region the op never allocated into, is a hard error (**SS1562**) — so
wrong-region free is unrepresentable. The arena lowers to real `malloc`/`free`
(one `free` per slab at `releaseRegion`) and JIT-runs.

### Bounds-checked buffers (WS1-115, §10.6)

A `Buffer` carries its length; there is **no indexing/offset syntax** in app
source. Element access goes through `standard.buffer` (`buffer.get`/`set`/
`length`/`slice`), and a read is **fallible** — an out-of-bounds index is a
`BufferBoundsError`, never UB:

```sem
readFirst invokes buffer.get
readFirst arg buffer Buffer payload
readFirst arg index ByteCount zeroIndex
readFirst out value Byte
readFirst catch boundsErr BufferBoundsError   # required — the OOB error path
```

A `buffer.get`/`at`/`read` with no `catch` for its `BufferBoundsError` is a hard
error (**SS1568**). `buffer.slice` returns a `Slice` that *borrows* the buffer (a
WS1-111 view: `mayEscape no`), so a slice that outlives its buffer is rejected
(SS1560). The bounds-check runtime lives in `standard.buffer` (WS1-119).

### FFI allocation wrapping (WS1-116, §26/§30.4)

A `runtimeBinding`/`intrinsic` that allocates foreign memory is `unsafe yes`, and
the raw foreign pointer is **never** exposed to app source — it re-enters as an
owned resource at the `.semsig` line:

```sem
allocBuffer is intrinsic
allocBuffer target c.malloc
allocBuffer out handle OwnedBuffer
allocBuffer unsafe yes
allocBuffer wrapsAs OwnedBuffer        # the opaque owned wrapper, not the raw ptr
allocBuffer cleanedBy c.free           # how it is released
allocBuffer allocator c.heap           # which allocator (region | c.heap)
```

An `unsafe yes` allocating binding missing any of `wrapsAs`/`cleanedBy`/
`allocator` is a hard error (**SS1569**) — a foreign allocation can only enter the
program as an `owns`-tracked resource, and `OpaquePointer` stays opaque (no
arithmetic in app source).

### Memory model: the language ↔ stdlib seam (WS1-122, §8/§26/§32.1)

The **language** owns the checked ownership/lifetime *vocabulary* —
`owns`/`cleanedBy`/`cleans`/`defer`, `borrows`/`lifetime`/`mayEscape`,
`consumes`/`takesOwnership`, `region`/`allocateIn`/`releaseRegion`,
`sharedState`/`guard` — and the checker that enforces it (SS1560–SS1571, SS3083).
The **stdlib** (`standard.memory`/`standard.buffer`) owns the *operations, types,
and the allocator capabilities*; raw `c.malloc`/`c.free` is a stdlib-internal
`unsafe` binding (WS1-116) and never app source (SS5000).

**They meet at the `.semsig`.** Each stdlib op publishes the annotations the
linter checks at *every* call site, with no hard-coding either way:

| stdlib op (`.semsig`) | published annotation | enforced at call sites by |
| --- | --- | --- |
| `memory.openRegion` | `owns region cleanedBy memory.releaseRegion` | SS1503 (cleanup), SS1564 (move) |
| `memory.allocateIn` | `out View`, `borrows region`, `mayEscape no` | **SS1560** (view-escape) |
| `buffer.slice` | `out Slice`, `borrows buffer`, `mayEscape no` | SS1560, SS1571 |
| `buffer.get` | `out Byte`, `catch BufferBoundsError` | SS1568 (must handle OOB) |
| allocating FFI leaf | `unsafe`/`wrapsAs`/`cleanedBy`/`allocator` | SS1569 |

So a value returned from `memory.allocateIn` is a borrowed `View` even though the
caller wrote no lifetime rows — the contract's `mayEscape no` propagates, and
returning the view out of the operation is rejected (SS1560). The stdlib declares
the contract; the language enforces it; agents `import`/`call` these modules and
learn the rules via `sem docs`/`.semsig`. Hand-rolled allocation or a raw pointer
in app source is rejected — the safe path is the only path.

#### Memory-safety model — Normative (§1J, WS1-121)

EAV is memory-safe by construction: there is no GC and no manual `free` in app
source, yet use-after-free, double-free, leaks, out-of-bounds, and data races are
unrepresentable or statically rejected. The model has six pillars, each enforced
above and reconciled with §10.6 (values), §29 #14 (memory), and §32.1 #9
(ownership):

1. **Value classes.** Primitives, `String`, `record`, `enum`, and `error` are
   plain values — compiler-managed, by-value, move semantics; they never take
   `owns`/`free`. Opaque resource handles are the only owned things.
2. **Ownership + cleanup.** A resource is the `owns`/`cleanedBy` producer; its
   cleanup must be `defer`-ed on every path (SS1503/SS3900) and runs in reverse
   registration order before each return.
3. **Borrowed views.** `borrows`/`lifetime`/`mayEscape` mark a non-owning view;
   a view never cleans (SS1566) and a `mayEscape no` view may not escape its
   source (SS1560), including across stdlib call boundaries.
4. **Transfer.** Ownership moves only via `consumes yes`/`takesOwnership`; reuse
   after a move is rejected (SS1564).
5. **Regions + bounds.** `region`/`allocateIn`/`releaseRegion` give arena
   allocation (allocate-many/free-once) gated by an allocator capability
   (SS1563), with wrong-region-free unrepresentable (SS1562) and
   use-after-release rejected (SS1561); `Buffer`/`Slice` access is bounds-checked
   (SS1568, never UB).
6. **FFI + concurrency.** A foreign allocator re-enters only as an owned wrapper
   (`unsafe`/`wrapsAs`/`cleanedBy`/`allocator`, SS1569); cross-task state is a
   guarded `sharedState` (SS3083/SS3084).

The **C-bug → EAV-defense coverage table** is generated from `DEFECT_LEDGER`
(X-101, `docs/defect-ledger.md`); every memory row maps to a WS1-110…120 item.

### Typestate protocols (X-091, §13/§15.6)

A `typestate <T>` declares a state machine over a type — its `state`s, the
`initial` state, and `allows <from> <target> <to>` transitions — so resource
open→use→close and the task RUNNING→…→CONSUMED lifecycle are one mechanism:

```sem
FileState is typestate
FileState for FileHandle
FileState state closed
FileState state open
FileState initial closed
FileState allows closed file.open  open     # file.open: closed -> open
FileState allows open   file.read  open     # file.read: only from open
FileState allows open   file.close closed   # file.close: open -> closed
```

A transition op invoked on a value not in its required `from` state is a hard
error (**SS3091**) — e.g. reading a `FileHandle` after `file.close` is rejected.
The check is flow-sensitive but linear: a value's state is tracked once known
(produced in-op, or after a prior transition), and an input's state is not
pre-judged until first transitioned (no false positives).

### Checked contracts (X-092, §6/§10.6)

`requires`/`ensures` promote `invariant`/`guarantee` to *checked* pre/post­
conditions on an operation, with numeric conditions `positive`/`nonNegative`/
`nonZero`:

```sem
charge requires positive amount      # precondition on the `amount` input
```

A `requires` is checked **at each call site**: a literal arg that violates it is a
hard error (**SS3092**); a literal that satisfies it is *statically discharged*
(no runtime check emitted); an unknown (runtime) arg gets a runtime assert that
**traps** on violation (never UB). So `charge` called with `-5` is a compile
error, with `7` compiles to a plain call, and with a runtime value compiles to a
checked call. (`ensures` is the symmetric postcondition row.)

### Call-level effect rows

`effect` on a `call` entity documents a side-effect the call produces at the
call-granularity level. This is finer-grained than the operation-level `effect`
summary, which the toolchain derives as a union of all call effects within the
operation:

```sem
appendAuditLog is call
appendAuditLog in recordPurchase
appendAuditLog invokes audit.append
appendAuditLog arg entry AuditEntry purchaseEntry
appendAuditLog out written Bool
appendAuditLog effect write storage.auditLog
```

Operation-level `effect` rows are either declared explicitly or synthesized by
`sem check` from the union of call-level effects. An explicit operation-level
`effect` that does not cover a call-level effect is a lint warning.

**Effect-union rule.** An operation's effective effect set is the union of its
own `effect` rows and the `effect` rows of every `call`, `task`, and `cleanup`
it activates (`do`/`start`/`defer`) — cleanup effects included, since deferred
cleanups run on every exit path. Operation-level `effect` rows are the declared
public summary of that union, and operation `uses` capabilities authorize the
whole union. The linter checks both directions: (1) every operation-level
`effect` is justified by some activated call/task/cleanup effect (or an explicit
external effect), and (2) the operation's `uses` capabilities grant every effect
in the union. A capability gap on a call/task/cleanup-level effect is reported
against the owning operation, naming the missing grant.

**Fallibility is declared, not inferred.** A call is fallible if and only if it
declares a `catch` row. Absence of `catch` is an explicit assertion that the
call cannot fail. If the call's `invokes` target resolves to a known signature
(stdlib, `.semsig`, or intrinsic, §26) that declares a `catch` error type,
omitting `catch` is a hard error; for a target with no known signature the
absence of `catch` is taken at face value — the call is treated as infallible —
and is unchecked. There is no
universal requirement that all calls have `catch` rows — infallible calls are
the norm for pure computations and format conversions.

### Error variable naming

**Per-call (canonical).** Each call binds its own error variable:

```sem
openDb catch openErr SqliteDatabaseOpenFailure
readCount catch queryErr SqliteQueryFailure
formatCount catch formatErr ConversionError
```

Preferred for agent patching and static analysis.

**Shared `err` (valid, concise).** Declare a mutable error variable and have
assignment-compatible catches bind to it:

```sem
lookupTask let err mutable TaskLookupError

loadTask catch err TaskLookupError
loadOwner catch err TaskLookupError
loadPermissions catch err TaskLookupError
```

Valid only when all error types are assignment-compatible with the declared `let`
type, and all failure paths go to a single label:

```sem
lookupTask at failed return nil err
```

### `discards`

`discards` documents deliberate result-dropping for all result slots (ok and
error) when neither `out` nor `catch` is present:

```sem
logDebug discards "debug logging result is intentionally ignored"
incrementHitCounter discards "metrics counter value is not used by the response"
```

`discards` payload must be a quoted string. Lint: a call whose target returns
non-void with no `out`, no `catch`, and no `discards` is an error.

A **fallible** cleanup call does not use `discards`: it declares a `catch`, and
the cleanup entity's `onFailure` policy consumes that error (`logAndSuppress`
logs it, `propagate` returns it). `discards` is only for genuinely infallible
results that are intentionally dropped (§15.6).

### Naming and cross-check

Drop the `*Call` suffix. The `is call` row makes the kind explicit.

Every `call` with `NAME in OP` is activated exactly once: normally by `OP do
NAME`, or — when the call is named by a `cleanup` entity's `call NAME` row — by
that cleanup's `OP defer CLEANUP` registration (the worker call runs when the
deferred cleanup fires, not at a `do`). A `call` entity has no lifecycle steps;
it completes synchronously when activated. Async invocations use `task`
(§15.5); deferred cleanup registrations use `cleanup` (§15.6).

### Invoking user operations

A call's `invokes` target resolves, in order, to:
1. a **bare in-module operation** — `invokes addTwoValues` calls the user
   `operation addTwoValues` declared in the same module (bare = internal, §3);
2. an **import-alias-dotted operation** — `invokes accounts.lookupAccount` calls
   an operation exported by the module imported under alias `accounts`;
3. a **compiler-derived target** — `compare.*` (§13) and the `<Type>.new` /
   `<Type>.<field>` / `<Enum>.<variant>` / `<Error>.<case>` targets (§10.5),
   which need no import;
4. an **intrinsic / stdlib target** — any target declared by an `intrinsic`
   signature in scope (§26).

When the target is an operation, the call binds it like any other: each `arg`
slot name matches one of the operation's `in` parameter names (types must
match), and the operation's `out` determines the call's `out`/`catch`:
- `out <type>` operation → the call binds `out <var> <type>`;
- `out Result <ok> <err>` operation → the call binds `out <var> <ok>` for the
  success value and `catch <var> <err>` for the error, exactly like a fallible
  stdlib call;
- void operation → the call binds neither `out` nor `catch`.

A synchronous operation (`async no`) is invoked through a `call` and run with
`do`; an `async yes` operation is invoked through a `task` and run with
`start`/`join` (§15.5). A bare `invokes` that resolves to no in-module operation
is a hard error (§17 #48).

**Target namespace and collisions.** Resolution is unambiguous because the four
sources occupy distinct shapes, and the case convention (§2) carries the
distinction:
- a **bare single token** (no dot) is always an in-module operation — operation
  names are camelCase, so they never collide with a type-derived target (which is
  dotted and PascalCase-led);
- a **dotted target led by a declared PascalCase type** is a construction/access
  target for that type (`Task.new`, `Task.title`, `NetworkError.timeout`,
  `ConsoleWriteError.ConsoleWriteFailed`, §10.5);
- a **dotted target led by an import alias** is an imported operation
  (`accounts.lookupAccount`);
- any **other dotted target** is a built-in or stdlib intrinsic (`compare.*`,
  `console.*`, `math.*`, `sqlite.*`).

Collision rules, all hard errors: an import alias may not equal a declared type
name in the same module (both could lead a dotted path); a bare operation name
may not equal a reserved word (§2) or a built-in lowercase namespace
(`compare`/`console`/`math`); and a `record` may not declare a field named `new`
(it would shadow the constructor segment, §10.5). Any genuinely ambiguous target
is rejected, not silently resolved (§17 #51).

**Conversion from v0.1:**

| v0.1 | v0.3 |
|---|---|
| `call NAME TARGET` | `NAME is call` + `NAME invokes TARGET` |
| *(implicit operation context)* | `NAME in <operation>` |
| `argument NAME slot TYPE value` | `NAME arg slot TYPE value` |
| `bind ok NAME var TYPE` | `NAME out var TYPE` |
| `bind value NAME var TYPE` | `NAME out var TYPE` |
| `bind error NAME var ERRTYPE` | `NAME catch var ERRTYPE` |
| `run NAME` | `OP do NAME` |
| `defer NAME TARGET ARGS...` | `CLEANUP is cleanup` entity + `OP defer CLEANUP` (§15.6) |
| `call NAME TARGET` + `NAME async yes` | `NAME is task` (§15.5) |
| `ignore void NAME` | deleted; add `NAME discards "..."` only if intentional |
| `writeHelloCall` → drop suffix | `writeHello` |

---

## 15.5. Task entity

A `task` entity is the async counterpart to `call`. It declares the same
invocation details as `call` — target, args, outputs, errors — but is activated
by `start`/`join`/`poll`/`cancel`/`detach` rather than `do`.

```sem
fetchUser is task
fetchUser in main
fetchUser invokes http.getJson
fetchUser arg url String userUrl
fetchUser out user User
fetchUser catch fetchUserErr HttpError
```

`task` entities do not have an `async` predicate — being a task implies async.
A `task` entity may declare `owns`, `cleanedBy`, and `effect` rows with the same
semantics as `call` (§15).

**Predicate vocabulary for `task`:**

| Predicate | Payload | Notes |
|---|---|---|
| `is` | `task` | entity declaration |
| `in` | `<operation>` | owning operation |
| `invokes` | `<target>` | external call target |
| `arg` | `<slot> <type> <value>` | input argument |
| `out` | `<var> <type>` | success output binding |
| `catch` | `<var> <errorType>` | error output binding |
| `discards` | `"<reason>"` | deliberate result drop |
| `owns` | `<var>` | resource ownership declaration |
| `cleanedBy` | `<cleanupName>` | cleanup entity for owned resource |
| `effect` | `<act> <resource>` | side-effect this task produces |
| `purpose` | `"<text>"` | documentation |

**Conversion from compact sugar:**

| Compact form | Canonical |
|---|---|
| `NAME is call` + `NAME async yes` | `NAME is task` (drop `async` row) |
| `OP start NAME` where `NAME is call` + `NAME async yes` | `OP start NAME` where `NAME is task` |

`sem fmt` performs this conversion automatically.

---

## 15.6. Cleanup entity

A `cleanup` entity represents a registered deferred cleanup action. It is
the canonical form for all cleanup registrations; the compound `defer CALL
onFailure POLICY because "..."` form is non-canonical sugar that lowers to a
cleanup entity.

```sem
closeDbCleanup is cleanup
closeDbCleanup in healthHandler
closeDbCleanup call closeDb
closeDbCleanup onFailure logAndSuppress
closeDbCleanup because "database connection must be closed after handler exits"
closeDbCleanup cleans db
```

The `call` predicate names the `call` entity that performs the actual close
(here `closeDb`, which keeps its natural verb name). `onFailure` names the error
policy. `because` documents the invariant. `cleans` names the binding (`db`)
declared as `owns` on the acquisition call.

**Naming convention.** Cleanup entity names end in `Cleanup` (`closeDbCleanup`);
the worker call keeps the plain verb name (`closeDb`). This keeps call names
natural while making cleanup entities obvious at a glance, and produces a clean
four-row triangle:

```
openDb owns db
openDb cleanedBy closeDbCleanup   # acquisition call → cleanup ENTITY
closeDbCleanup cleans db          # cleanup entity → owned binding
closeDbCleanup call closeDb       # cleanup entity → worker call
```

**Predicate vocabulary for `cleanup`:**

| Predicate | Payload | Notes |
|---|---|---|
| `is` | `cleanup` | entity declaration |
| `in` | `<operation>` | owning operation |
| `call` | `<callName>` | **required**: call entity that performs the cleanup action |
| `onFailure` | `logAndSuppress` \| `propagate` | error policy — required iff the worker `call` has `catch` |
| `because` | `"<reason>"` | invariant documenting why cleanup is required (required by `logAndSuppress`) |
| `cleans` | `<var>` | **required**: binding acquired by the corresponding `owns` row |
| *(metadata)* | `purpose` / `note` / `tag` (§6) | optional documentation rows, placed after the structural rows |

**Error policies:**

| Policy | Meaning |
|---|---|
| `logAndSuppress` | Log the cleanup error; do not propagate it to the caller (safe default) |
| `propagate` | Propagate the cleanup error (overrides any in-flight error) |

There is no silent-drop policy. A `logAndSuppress` cleanup must declare a
`catch` on its worker call so there is an error value to log; a cleanup whose
worker cannot fail needs no policy at all. (A third `ignore` policy was
considered and deferred: even gated behind `because`, it invites agents to
silence cleanup failures just to satisfy the linter. `logAndSuppress` is the
safe default.)

**Constraint: `cleans` ↔ `owns` cross-check.**  
`CLEANUP cleans VAR` is valid only if some `call` or `task` in the same
operation has `NAME owns VAR`. The linter raises a hard error otherwise.

**Required rows.** A `cleanup` entity must declare exactly one `cleans` row and
exactly one `call` row. There is no ownerless/generic cleanup in v0.3: for a
side effect that releases nothing it owns (e.g. "flush logs"), use a plain
`call` activated by `do`, not a `cleanup` entity.

**`onFailure` is conditional on worker fallibility.** Declare `onFailure` on a
cleanup entity **iff** its worker `call` declares `catch`:
- worker has `catch` (fallible) → `onFailure` is required; the policy consumes
  the error (`logAndSuppress` logs it, `propagate` returns it);
- worker has no `catch` (infallible) → `onFailure` must be omitted — there is no
  error to route, so a policy would be clutter.

**Unused worker output.** A cleanup worker `call` with an `out` row and no
`catch` must declare `discards "<reason>"` for that output unless the output is
consumed on a control path. Most cleanup workers return `Void` or are fallible
(`catch`), so this is rare.

**Activation.** Cleanup entities are registered via `OP defer CLEANUP`. The
runtime executes registered cleanup entities in reverse registration order when
the operation exits (normal or failure path), consistent with the `defer`
contract in §13.

**Conversion from compound defer sugar:**

```
# Sugar (accepted, not canonical):
healthHandler defer closeDb onFailure logAndSuppress because "..."

# Canonical form produced by sem fmt:
closeDbCleanup is cleanup
closeDbCleanup in healthHandler
closeDbCleanup call closeDb
closeDbCleanup onFailure logAndSuppress
closeDbCleanup because "..."
closeDbCleanup cleans db
healthHandler defer closeDbCleanup
```

`sem fmt` generates the cleanup entity name deterministically from the worker
call name plus a `Cleanup` suffix (`closeDb` → `closeDbCleanup`). If a cleanup
entity with `call closeDb` already exists for that operation, the formatter
reuses it instead of generating a new one; if the generated name collides with a
different entity, it appends the lowest free numeric suffix (`closeDbCleanup2`).
Both rules keep re-running `sem fmt` idempotent.

---

## 16. DSL islands — SQL, JSON, HTML

**Out of scope for this spec.** JSON encoding/decoding (runtime codec) and
trust-boundary request validation (input sanitization, schema verification) are
application patterns built using call entities targeting the `json` and `http`
stdlib modules. Their idioms belong in a cookbook/guide, not in this syntax
specification.

Islands attach to a `storage` or `htmlTemplate` entity via a `body <kind>` row.
The island body is an indented block — the only place in SemanticScript where
whitespace is semantic (§2). **Indentation rule:** island lines are indented with
**spaces only** (a literal tab in an island body is a hard error); every body line
shares a common leading-space prefix of at least one space, which the toolchain
strips uniformly while preserving the relative indentation inside the body
verbatim. The first row indented back to column 1 (a token-bearing row) ends the
island. Mixed tabs/spaces in the prefix is a hard error.

```sem
openSql is storage
openSql scope module
openSql type SqlText
openSql mutability immutable
openSql body sql
    SELECT count(*) FROM tasks WHERE status = 'open'
```

The first column-1 token-bearing row ends the island.

`<kind>` must match the declared type:

| type | body kind |
|---|---|
| `SqlText` | `sql` |
| `JsonText` | `json` |
| `HtmlTemplate` | `html` |

HTML templates use the `htmlTemplate` kind:

```sem
taskRow is htmlTemplate
taskRow body html
    <li class="task">{{title}} — {{status}}</li>
```

### Island content rules

`sql`: `?` placeholders only; no `{hole}` interpolation. Each `?` binds
positionally, left-to-right, to the parameter `arg` rows of the call that
executes the statement (the args following the `database` and `sql` args), in
document order. The number of `?` placeholders must equal the parameter-arg
count; a mismatch is a hard lint error.

`json`: validated and canonicalized at build time.

`html`: `{{hole}}` and `{{rec.field}}` are auto-escaped by sink context. Legacy
single-brace holes such as `{title}` are hard errors. Dynamic holes in
URL-bearing attributes (`href`, `src`, `action`, `formaction`, `poster`) must
be typed `HtmlSafeUrl`; plain `String` is valid for text and non-URL quoted
attributes only. `{{rec.field}}` dots are inside island foreign content and are
exempt from §3's no-internal-dots rule.

**Rejected hole contexts.** Dynamic `{{holes}}` in `<script>`, `<style>`, HTML
comment content (`<!-- {{hole}} -->`), and raw tag attribute names are hard
parse errors. The template parser rejects these outright — no escaping strategy
makes dynamic content safe in those positions.

**`HtmlTrustedFragment`.** An `HtmlTrustedFragment` is a pre-sanitized HTML
fragment that bypasses auto-escaping when rendered. It is produced only by
calls that have been explicitly marked as trust boundaries (e.g.,
`html.trustFragment`). Rules:
- `HtmlTrustedFragment` values may not originate from user-controlled input
  without an explicit sanitization call; the linter cannot enforce this
  statically but the convention is required.
- Template holes typed `HtmlTrustedFragment` render the fragment bytes
  verbatim — no escaping is applied.
- `html.fragmentConcat` takes two or more `HtmlFragment` or
  `HtmlTrustedFragment` values and returns an `HtmlFragment`.
- `HtmlTrustedFragment` is NOT the same as `HtmlFragment`: `HtmlFragment` is
  the result of template rendering (auto-escaped), while `HtmlTrustedFragment`
  is a bypass token for pre-sanitized content. Using one where the other is
  expected is a type error.

### Template rendering

Template rendering requires `standard.html` to be imported in the module:

```sem
taskWeb imports html standard.html
```

A template is rendered by calling `html.render`. Arg slot names must exactly
match hole names declared in the template:

```sem
renderTask is call
renderTask in listTasks
renderTask invokes html.render
renderTask arg template HtmlTemplate taskRow
renderTask arg title String taskTitle
renderTask arg status String taskStatusText
renderTask out fragment HtmlFragment
```

**Hole escaping by arg type.** `html.render` auto-escapes plain text holes
(`String` and other scalar types) by sink context. Holes whose arg type is
already-safe HTML are passed through verbatim: `HtmlSafeUrl` (a validated URL),
and `HtmlFragment`/`HtmlTrustedFragment` (a rendered/trusted fragment nested into
an outer template — escaping already-escaped markup would corrupt it). This is
how a page template embeds a component's rendered fragment as a raw `{{frag}}`
hole.

For `{{rec.field}}` holes, the arg provides the record binding; the runtime
extracts the named field. The arg type must be a `record` entity with the
matching field name declared (§10):

```sem
renderTask arg task Task taskRecord    # supplies {{task.title}}, {{task.status}}
```

**Mixed scalar and record holes.** Scalar holes `{{name}}` bind by arg slot
name `name`. Record holes `{{rec.field}}` bind by arg slot name `rec`. The two
forms are independent — a template may use both:

```sem
rowTemplate is htmlTemplate
rowTemplate body html
    <li>{{prefix}}{{task.title}} — {{task.status}}</li>

renderRow is call
renderRow in listTasks
renderRow invokes html.render
renderRow arg template HtmlTemplate rowTemplate
renderRow arg prefix String labelPrefix    # scalar hole
renderRow arg task Task taskRecord         # record holes
renderRow out fragment HtmlFragment
```

**Multiple records.** Use distinct arg slot names for each record binding:

```sem
renderAssignment is call
renderAssignment invokes html.render
renderAssignment arg template HtmlTemplate assignmentRow
renderAssignment arg task Task taskRecord      # {{task.title}}, {{task.status}}
renderAssignment arg user User userRecord      # {{user.name}}, {{user.email}}
renderAssignment out fragment HtmlFragment
```

Slot names in arg rows must be unique within a call. A hole in the template
that has no matching arg slot name is a hard lint error.

Type mismatch between an arg type and the declared hole sink context is a hard
lint error (e.g., passing `String` where `HtmlSafeUrl` is required for an
`href` hole).

**Conversion from v0.1:**

| v0.1 | v0.3 |
|---|---|
| `storage module immutable NAME SqlText` + island | `NAME is storage` + rows + `NAME body sql` + island |
| `jsonBody NAME` | `NAME body json` |
| `html template NAME` + island | `NAME is htmlTemplate` + `NAME body html` + island |

---

## 17. Linting invariants

### Structural invariants

1. Every entity has exactly one `is` row as its first row.
2. Every `call` is activated exactly once in its owning operation: by `OP do
   NAME`, or — for a worker call named by a `cleanup` entity's `call NAME` row —
   by that cleanup's `OP defer CLEANUP` registration. A `call` is never the
   direct target of `start` or `defer`.
3. Step-target restrictions (hard errors):
   - `OP do NAME` where `NAME` is a `task` or `cleanup` entity.
   - `OP start NAME` (or `join`/`poll`/`cancel`/`detach`) where `NAME` is a
     `call` or `cleanup` entity.
   - `OP defer NAME` where `NAME` is a `call` or `task` entity.
4. Every `do NAME`, `start NAME`, and `defer NAME` references a declared entity
   whose `in` row names the same operation.
5. Every `effect` is covered by a `uses` capability whose `grants` matches
   action + resource, or is flagged as a lint warning.
6. `branch ifError CALL` after a sync call requires a preceding `do CALL`.
   `branch ifError TASK` after an async task requires a preceding `join TASK`.
   `poll TASK` alone is not a valid predecessor. Missing `catch` on the named
   call or task is a hard error.
7. `do TASK` where `TASK` is a `task` entity is a hard lint error (use `start`).
8. Every `branch if VAR` and `branch ifFalse VAR` requires `VAR` to be a `Bool`
   binding in scope at that step.
9. At the target label of `branch ifError CALL goto LABEL`, the catch variable
   declared by `CALL catch <var> <type>` is in scope. The linter tracks the
   most-recently-bound value for shared variable names.
10. Return arity must match the operation's `out`: no payload for void, one
    payload for single-value, exactly one `nil` slot for `Result`.
11. Every `goto`/`branch ... goto LABEL` target has exactly one `OP at LABEL
    ...` row in the same operation.
12. Every `at LABEL` label name is unique within the operation.
13. Every `at LABEL` is referenced by at least one `goto`/`branch ... goto
    LABEL` row; an unreferenced label is dead (SS1012, warning).
14. `loop`, `while`, `each`, `break`, `continue`, and `end` are not valid step
    predicates; any step row using these is a hard parse error.
15. Irreducible control flow is a lint warning in v0.3, not an error.
16. Owned resources with required cleanup must be cleaned on every ownership
    path via `defer CLEANUP` (where CLEANUP is a `cleanup` entity), registered
    immediately after the successful producer branch.
17. Deferred cleanup entities run in reverse registration order before every
    `return`.
18. `onFailure propagate` on a `cleanup` entity requires (a) the cleanup's
    `call` entity to have a `catch` row and (b) the enclosing operation to
    declare `out Result <ok> <err>`. Using `propagate` in a void or
    single-value operation is a hard lint error.
19. `onFailure logAndSuppress` on a `cleanup` entity requires a `because
    "reason"` quoted string on the cleanup entity. `logAndSuppress` without
    `because` is a hard lint error.
20. Every started `task` must be `join`-ed, `cancel`-ed, or `detach`-ed before
    `return`. Unresolved started task at operation exit is a hard error.
21. `cancel TASK` requires the task to have been `start`-ed on the current path.
22. `branch ifCanceled TASK` requires a preceding `cancel TASK` + `join TASK`.
23. `columnText`/`columnBlob`/`columnName` sqlite column results must be consumed
    before the next read on the same statement.
24. Multi-write sequences on the same resource require a transaction.
25. A non-void call with no `out`, no `catch`, and no `discards` is an error.
26. No dotted internal entity references. Dots only in external target paths and
    island body content.
27. `nil`, `true`, `false`, and all reserved words (§2) may not be used as
    entity, variable, or type names.
28. Declaration rows (including metadata rows) may be reordered; step rows
    may not.
29. `out` naming an existing `immutable` binding is a hard error. `out` naming
    an existing `mutable` binding of compatible type rebinds it (§12).
30. Duplicate field names within a `record` entity are a hard error. Duplicate
    variant names within an `enum` entity are a hard error.
31. `branch else goto LABEL` without any preceding `branch <guard>` row in the
    same operation produces a formatter warning to use `goto LABEL` instead.
32. Identical routes (same method + path) on a `webServer` entity are a hard
    lint error.
33. Template rendering call arg slot names must exactly match hole names in the
    referenced `htmlTemplate`.
34. Passing `String` to an `HtmlSafeUrl`-required hole is a hard lint error.
35. A fallible call (declares `catch`) with no `branch ifError CALL` on any
    reachable path and no `discards` row is a lint warning: "fallible call has
    no error handling path." The programmer has declared the call can fail but
    provided no error route. This is a warning, not a hard error, to allow
    intentional suppression with `discards`. **Exempt:** a worker call named by
    a `cleanup` entity's `call` row — its error is routed by the cleanup's
    `onFailure` policy, not by a `branch ifError`.
36. `branch ifOut CALL` on a fallible call (one that has both `out` and `catch`)
    is a lint warning unless a `branch ifError CALL` has already been taken on
    that path (establishing the non-error path). Using `ifOut` before the error
    case is handled may compare an output value that is invalid in the error
    state. The warning: "ifOut on fallible call before error branch." In
    canonical EAV, `ifOut` is non-canonical sugar; `sem fmt` lowers it to a
    comparison call + `branch if`.
37. `alias for` target may use `<importAlias>.<typeName>` form (§7) only in
    `for` rows. All other type positions must use bare names.
38. A project `entry` operation in canonical EAV must have an explicit `MODULE
    exports NAME` row for each `entry` in that module. Missing export is a hard
    error (MD1013).
39. `CALL owns VAR` without a corresponding `CALL cleanedBy CLEANUPNAME` on the
    same call entity is a lint warning: "owned resource has no registered
    cleanup." `CLEANUP cleans VAR` where no call or task in the same operation
    has `owns VAR` is a hard error.
40. `branch ifOut` and `branch ifValue` are non-canonical sugar. `sem fmt` lowers
    them to a comparison call + `branch if`. In strict canonical mode
    (`sem lint --strict`), using them without first running `sem fmt` is an
    info diagnostic: "non-canonical sugar; run sem fmt to normalize."
41. Every `cleanup` entity must declare exactly one `cleans` row and exactly one
    `call` row. A cleanup with no `cleans` is a hard error (use a plain `call`
    for ownerless side effects).
42. A `cleanup` entity must declare `onFailure` if and only if its worker `call`
    declares `catch`. `onFailure` on an infallible worker, or a missing
    `onFailure` on a fallible worker, is a hard error.
43. A worker `call` named by a `cleanup` entity's `call` row must not also be
    activated by `OP do CALL` — it runs only when the cleanup fires via `defer`.
    A `do` on a cleanup worker is a hard error.
44. A cleanup worker `call` with an `out` row and no `catch` must declare
    `discards` unless its output is consumed on a control path.
45. `branch ifOut`/`ifValue` comparators on a `Bool` or payloadless-`enum`
    operand are restricted to `equals`/`notEquals`; `greaterThan`/`lessThan` on
    them is a hard error. Data-carrying enums may not be compared (§13).
46. Entity names are unique within a module; a duplicate `is` declaration for an
    existing name is a hard error.
47. Binding names are unique within an operation: a `let`, `in` parameter, or
    `out` binding may not shadow another name already in scope in that operation.
    Rebinding a `let mutable` via a compatible `out` is the one allowed reuse
    (§12).
48. A bare `invokes` target must resolve to an `operation` declared in the same
    module; an unresolved bare target is a hard error. A dotted `invokes` target
    must resolve to an imported exported operation, a compiler-derived target
    (§10.5, §13), or an `intrinsic` in scope.
49. A construction/access target (§10.5) must match its type: `<Record>.new`
    requires one `arg` per declared field with matching name and type;
    `<Record>.<field>` must name a declared field; `<Enum>.<variant>` and
    `<Error>.<case>` must name a declared variant/case and supply the payload
    `arg` if and only if one is declared.
50. An operation with `body runtimeBinding`/`body intrinsic` must declare every
    `effect` its binding performs, covered by `uses` (§8). A non-step body in
    application source (not a stdlib/`.semsig` module) is a hard error — an
    unverifiable authority assertion confined to the reviewed stdlib boundary
    (§11).
51. `invokes` target resolution must be unambiguous (§15): an import alias may
    not equal a declared type name; a bare operation name may not equal a
    reserved word or a built-in lowercase namespace (`compare`/`console`/`math`);
    a `record` may not declare a field named `new`. Any ambiguous target is a
    hard error.
52. `branch ifVariant VALUE` requires `VALUE` to be an `enum` or `error` binding
    in scope and `VARIANT` to be one of its declared variants/cases. If a closed
    `enum`/`error` value is matched but not all variants are covered and no
    default transfer follows the series, the linter warns (non-exhaustive match).
    The canonical default is a plain `goto LABEL`; `branch else` is its
    non-canonical sugar (§13) and `sem fmt` lowers it to `goto`.
53. `bind PAYLOAD` on a `branch ifVariant` row is valid only when the matched
    variant declares a payload; `PAYLOAD` is in scope only on the target label's
    path (catch-style, §25). Binding on a payloadless variant, or referencing
    `PAYLOAD` off that path, is a hard error.
54. `suppress <CODE> because "<reason>"` (§30.6.2) requires both a real diagnostic
    code and a quoted `because`; a `suppress` row missing either, or naming an
    unknown code, is a hard error. Suppression is scoped to its subject entity and
    that one code — no file-wide or wildcard suppression.
55. `forTarget <target>` (§30.3.1) must name a target the project builds, and
    `forPlatform <name>` must name a declared `platform` (§28.1); the project's
    `entry` entity must resolve for every built target. `forTarget`,
    `forPlatform`, and `suppress` are valid on any entity kind and sort after
    structural + metadata rows (§22).

### Metadata invariants (MD rules)

**Module metadata (always required):**
MD1001: Every `module` must have exactly one `purpose` row. [error]
MD1002: Every `module` must have at least one `invariant` row. [error]

**Exported and entry operation metadata (required):**
MD1011: Exported operation or project `entry` operation missing `purpose`. [error]
MD1012: Exported operation or project `entry` operation missing `invariant`. [error]
MD1013: Project `entry` operation in canonical EAV has no corresponding `MODULE exports NAME` row. [error]

**Private operation metadata (recommended):**
MD1021: Private (non-exported, non-entry) operation missing `purpose`. [warning]
MD1022: Private operation missing `invariant`. [info]

**Generated/runtimeBinding operation metadata:**
MD1031: Generated or `runtimeBinding` operation missing `purpose`. [off]
MD1032: Generated or `runtimeBinding` operation missing `invariant`. [off]

**Payload and structural rules:**
MD1040: Metadata rows must not appear inside island bodies.
MD1041: Metadata predicates must not be used as step row predicates.
MD1042: `purpose` payload must be a quoted string.
MD1043: `invariant` payload must be a quoted string.
MD1044: `tag` payload must be a bare identifier.
MD1045: `deprecated` payload must be a quoted string.
MD1046: At most one `purpose` row per entity; a duplicate is a hard error. (Whether `purpose` is *required* is set by the visibility tier — MD1011/MD1021/MD1031.)
MD1047: `owner` payload must be a bare identifier.
MD1048: `label` metadata predicates are restricted to `purpose`, `note`,
`rationale`, `risk`, `tag`. Other metadata predicates on `OP label LABEL ...`
rows are hard errors.

### Diagnostic repair suggestions

The linter emits repair suggestions alongside every error. Format:

```
SS<code>: <description>
Found:
  <offending row>
<context note>

Suggested fix:
  <concrete row(s) to insert or change>
```

**Example — missing activation before ifError:**

```
SS1305: branch ifError openDb requires a preceding do openDb or join openDb.
Found:
  healthHandler branch ifError openDb goto failed
No preceding activation found for openDb in this step sequence.

Suggested fix:
  Insert before this row:
  healthHandler do openDb
```

**Example — owned resource missing cleanup:**

```
SS1502: call openDb declares `owns db` but no cleanup entity with `cleans db`
is registered on all paths where openDb succeeds.
Found:
  healthHandler branch ifError openDb goto failedNoDb
No defer <cleanup> found after this branch.

Suggested fix:
  Declare a cleanup entity and register it after branch ifError openDb:

  closeDbCleanup is cleanup
  closeDbCleanup in healthHandler
  closeDbCleanup call closeDb
  closeDbCleanup onFailure logAndSuppress
  closeDbCleanup because "<reason>"
  closeDbCleanup cleans db

  Insert after branch ifError openDb goto failedNoDb:
  healthHandler defer closeDbCleanup

  Also declare the call entity if not already present:
  closeDb is call
  closeDb in healthHandler
  closeDb invokes sqlite.closeDatabase
  closeDb arg database SqliteDatabase db
  closeDb catch closeErr SqliteDatabaseCloseFailure
```

**Example — async task unresolved at return:**

```
SS1610: started task fetchUser is not joined, canceled, or detached before return.
Found:
  main return dashboard nil
fetchUser state: RUNNING (started at step 3, never joined/canceled/detached).

Suggested fix:
  Insert before return:
  main join fetchUser
  main branch ifError fetchUser goto fetchFailed
  OR:
  main detach fetchUser "reason fetchUser result is not needed before return"
```

---

## 18. Worked example — Hello World

```sem
HelloWorld is project
HelloWorld module examplesHelloWorld
HelloWorld target console
HelloWorld entry main

examplesHelloWorld is module
examplesHelloWorld path examples.helloWorld
examplesHelloWorld exports main
examplesHelloWorld purpose "Contain the Hello World console entry operation"
examplesHelloWorld invariant "Exports main as the only project entry operation"

ExitCode is alias
ExitCode for Int32
ExitCode purpose "Process exit status: 0 for success, non-zero for failure"

stdoutWriter is capability
stdoutWriter grants write console.stdout
stdoutWriter purpose "Allow controlled writes to standard output"
stdoutWriter invariant "Only grants write access to console.stdout"

ConsoleWriteError is error
ConsoleWriteError purpose "Represent failures from console output operations"

ConsoleWriteFailed is errorCase
ConsoleWriteFailed of ConsoleWriteError
ConsoleWriteFailed payload Int32
ConsoleWriteFailed purpose "Represent a failed stdout write with a platform status code payload"

main is operation
main out ExitCode
main effect write console.stdout
main uses stdoutWriter
main memory heap no
main async no
main purpose "Write hello world and return a process exit code"
main invariant "All stdout writes go through stdoutWriter"
main invariant "Returns writeFailedExitCode on any write failure"

main let helloText immutable String "hello world"
main let successExitCode immutable ExitCode 0
main let writeFailedExitCode immutable ExitCode 1

main do writeHello
main branch ifError writeHello goto failed
main return successExitCode

main at failed return writeFailedExitCode

writeHello is call
writeHello in main
writeHello invokes console.writeLine
writeHello arg text String helloText
writeHello catch writeError ConsoleWriteError
writeHello purpose "Write the greeting text to stdout"
writeHello risk "May fail if stdout is closed or unavailable"
```

---

## 19. Worked example — web handler with database

```sem
TaskApp is project
TaskApp module taskWeb
TaskApp target webServer
TaskApp entry appServer

taskWeb is module
taskWeb path app.taskWeb
taskWeb imports sqlite standard.sqlite
taskWeb imports http standard.http
taskWeb imports convert standard.convert
taskWeb exports healthHandler
taskWeb exports appServer
taskWeb purpose "Serve the task management web application"
taskWeb invariant "All database access goes through databaseAccess capability"

databaseAccess is capability
databaseAccess grants readWrite database
databaseAccess purpose "Allow read and write access to the task database"

responseWriter is capability
responseWriter grants write http.response
responseWriter purpose "Allow writing HTTP responses to clients"

openSql is storage
openSql scope module
openSql type SqlText
openSql mutability immutable
openSql body sql
    SELECT count(*) FROM tasks WHERE status = 'open'

appServer is webServer
appServer host "127.0.0.1"
appServer port 8080
appServer route GET "/health" healthHandler

healthHandler is operation
healthHandler in request HttpRequest
healthHandler in response HttpResponse
healthHandler out Int32
healthHandler effect readWrite database
healthHandler effect write http.response
healthHandler uses databaseAccess
healthHandler uses responseWriter
healthHandler memory heap no
healthHandler async no
healthHandler purpose "Return open task count as plain text"
healthHandler invariant "Responds 500 on any database failure or write failure"
healthHandler invariant "closeDbCleanup is deferred immediately after successful openDb"

healthHandler let databasePath immutable String "tasks.db"
healthHandler let okStatus immutable HttpStatusCode 200
healthHandler let failStatus immutable HttpStatusCode 500
healthHandler let successStatus immutable Int32 0
healthHandler let textContentType immutable HttpContentType "text/plain; charset=utf-8"
healthHandler let errorBody immutable HttpTextBody "Internal Server Error"

healthHandler do openDb
healthHandler branch ifError openDb goto failedNoDb
healthHandler defer closeDbCleanup
healthHandler do readCount
healthHandler branch ifError readCount goto failed
healthHandler do formatCount
healthHandler branch ifError formatCount goto failed
healthHandler do writeOk
healthHandler do checkWriteOk
healthHandler branch if writeOkCheck goto writeFailed
healthHandler return writeResult

healthHandler at failed do writeFail
healthHandler return failResult
healthHandler at failedNoDb do writeFailNoDb
healthHandler return failNoDbResult
healthHandler at writeFailed return writeResult

openDb is call
openDb in healthHandler
openDb invokes sqlite.openDatabase
openDb arg path String databasePath
openDb arg mode SqliteOpenMode readWriteCreate
openDb out db SqliteDatabase
openDb catch openErr SqliteDatabaseOpenFailure
openDb owns db
openDb cleanedBy closeDbCleanup
openDb purpose "Open the task database for reading"
openDb risk "Fails if the database file is missing or locked"

closeDbCleanup is cleanup
closeDbCleanup in healthHandler
closeDbCleanup call closeDb
closeDbCleanup onFailure logAndSuppress
closeDbCleanup because "database cleanup failure must not replace the response status"
closeDbCleanup cleans db

closeDb is call
closeDb in healthHandler
closeDb invokes sqlite.closeDatabase
closeDb arg database SqliteDatabase db
closeDb catch closeErr SqliteDatabaseCloseFailure

readCount is call
readCount in healthHandler
readCount invokes sqlite.queryScalarInt64
readCount arg database SqliteDatabase db
readCount arg sql SqlText openSql
readCount out openTaskCount Int64
readCount catch queryErr SqliteQueryFailure

formatCount is call
formatCount in healthHandler
formatCount invokes convert.convertSignedInt64ToString
formatCount arg inputValue Int64 openTaskCount
formatCount out countText String
formatCount catch formatErr ConversionError

writeOk is call
writeOk in healthHandler
writeOk invokes http.responseText
writeOk arg response HttpResponse response
writeOk arg status HttpStatusCode okStatus
writeOk arg body HttpTextBody countText
writeOk arg contentType HttpContentType textContentType
writeOk out writeResult Int32

checkWriteOk is call
checkWriteOk in healthHandler
checkWriteOk invokes compare.notEqualsInt32
checkWriteOk arg left Int32 writeResult
checkWriteOk arg right Int32 successStatus
checkWriteOk out writeOkCheck Bool

writeFail is call
writeFail in healthHandler
writeFail invokes http.responseText
writeFail arg response HttpResponse response
writeFail arg status HttpStatusCode failStatus
writeFail arg body HttpTextBody errorBody
writeFail arg contentType HttpContentType textContentType
writeFail out failResult Int32

writeFailNoDb is call
writeFailNoDb in healthHandler
writeFailNoDb invokes http.responseText
writeFailNoDb arg response HttpResponse response
writeFailNoDb arg status HttpStatusCode failStatus
writeFailNoDb arg body HttpTextBody errorBody
writeFailNoDb arg contentType HttpContentType textContentType
writeFailNoDb out failNoDbResult Int32
```

---

## 20. Conversion procedure

Work one operation at a time.

1. **Header.** `operation X` → `X is operation`. Convert `input`/`output`/
   `effect`/`memory`/`async`/`purpose`/`invariant`/`useCapability` to
   declaration rows (§11). Delete all `authority` rows; verify each effect is
   covered by a `uses` capability (§8). Add `purpose` and `invariant` to modules
   (always required) and to exported/entry operations (required); apply the
   visibility tier table from §6 for private and generated operations.
2. **Storage.** Convert each `storage local ...` to a `let` row (§12). Promote
   each `storage module ...` and DSL island to a top-level entity (§12, §16).
3. **Steps.** Scan the operation body in document order. Each `run X` → `OP do
   X`. Promote `call async yes` → `task` entity (`sem fmt` does this
   automatically). Async lifecycle rows become `start`/`join`/`poll`/`cancel`/
   `detach` (§13). Each `defer X onFailure POLICY because "..."` → declare a
   `cleanup` entity + `OP defer CLEANUPNAME` (§15.6). Each `branch` → refined
   branch with `goto` (§13). Each `return`/`label`/`jump` → refined form (§13).
   Replace `branch ifOut`/`ifValue` sugar with a comparison call + `branch if`.
4. **Async resolution.** Verify every started `task` is joined, canceled, or
   detached. Add `join TASK` at all `ifReady` landing labels where task outputs
   are needed. Use per-task failure labels to keep error variables unambiguous.
5. **Call details.** For each `call X TARGET` + its `argument`/`bind` rows,
   emit a call entity block (§15). Delete `run` and `ignore void` rows. Drop
   the `*Call` suffix. For any acquired resource, add `owns` + `cleanedBy` rows
   to the call entity, and declare the corresponding `cleanup` entity (§15.6).
   Cleanup calls are activated by `defer CLEANUP`, not `do`.
6. **Error cases.** `error NAME` → `NAME is error`. Each `errorCase NAME CASE
   TYPE` → three-row promoted entity (§9). Replace dotted references with bare
   names.
7. **Cross-check.** Every `do X` has `X in OP` + `X is call`. Every `start X`
   has `X in OP` + `X is task`. Every `defer X` has `X in OP` + `X is cleanup`.
   Every call/task has exactly one activation. Every `branch ifError X` has the
   correct predecessor (`do` or `join`). Every started task resolved. Every `at
   LABEL` referenced. Every `goto LABEL` has a matching `at`.
8. **Type declarations.** For any named types used as `out` or `arg` types that
   are not primitive and not imported, declare `record`, `enum`, or `alias`
   entities (§10). Add `repr` rows for enums with ABI-fixed discriminants. Export
   public types from the module. Replace all v0.1 suffixed variant references
   (e.g., `readWriteCreateSqliteOpenMode`) with bare variant names (`readWriteCreate`).
9. **Top-level entities.** Convert `project`, `module`, `capability`, `webServer`
   blocks (§7, §8, §14). Add `purpose`/`invariant` to all modules and exported
   operations. Add `exports` rows for public entities.
10. **Label metadata.** Replace standalone `label NAME` comments with
    `OP label NAME purpose "..."` declaration rows on the owning operation (§6).
11. **HTML rendering.** Replace v0.1 template calls with `html.render` call
    entities; arg slot names must match template hole names; add `imports html
    standard.html` (§16).
12. **Mutable rebinding.** Where a call's `out` names an existing `let mutable`
    binding, no change is needed — the rebind is implicit. Verify the binding was
    declared `mutable` and the types are compatible (§12).
13. **Async poll/detach flows.** For each fire-and-poll pattern, verify `join`
    appears at every `ifReady` landing label before outputs are used. For
    fire-and-forget, add `detach TASK "reason"` with a quoted rationale (§13).
14. **Lint.** Run against invariants in §17. Fix all violations including MD
    rules. For memory policy rows, use `memory heap yes|no`, `memory stack N`,
    `memory max N` forms (§11).

---

## 21. Adoption gate and row-count measurement

v0.3 is expected to increase raw row count in most applications. This is an
acknowledged trade, not an oversight. The trade is:

```
more rows
for:
  uniform parsing — every row is subject + predicate + payload; patch by pattern (predicates are kind-scoped, §5)
  grep-locality — every entity kind, predicate, and step is findable by pattern
  visible cleanup ownership — defer always adjacent to owned handle creation
  explicit async ownership — lifecycle always traceable from start to resolve
  machine-readable documentation — purpose/invariant greppable per entity
  safer HTML contracts — double-brace auto-escape, HtmlSafeUrl typed holes
  reduced silent failures — discards, catch, and ifError all require presence
```

**Row-count metric.** A row is any non-blank, non-comment line in the source
file. Comment lines begin with `#` at column 1 and are excluded. Blank lines
(containing only whitespace) are excluded. Island body lines (indented under a
`body <kind>` row, §16) count as rows — they are source content. The percentage
increase is computed per module (file), not globally:

```
row_increase = (v0.3_rows - v0.1_rows) / v0.1_rows × 100
```

A single module with +30% is a gate failure even if the overall codebase
averages +15%. Use `sem lower --to eav` (proposed; §24 — today use the closest
existing surface, `sem migrate-syntax`) to get the canonical row count; count
the output with:

```bash
grep -Ev '^[[:space:]]*$|^#' FILE | wc -l
```

This excludes blank lines and full-line comment lines, and correctly counts
rows with trailing comments (the row itself is content).

**The adoption gate.** v0.3 adoption is justified only if a real converted app
meets all of:

0. **Round-trip safety (precondition).** `sem fmt` must be semantics-preserving
   and idempotent across surfaces: compact → EAV → compact and current → EAV →
   current must round-trip without changing program meaning, proven by a feature
   test that fails under a no-op lowering. Given the known `htmlBody`
   de-indentation hazard in the current formatter, this gate is mandatory before
   any conversion metric is trusted.
1. Row count, measured **after canonicalization**, by surface:
   - **Compact / current authoring surface:** +20% max over the converted
     application's current form.
   - **Canonical primitive EAV surface:** +35% max. Strict primitive EAV is
     intentionally more verbose; the extra budget pays for the
     `call`/`task`/`cleanup` split, ownership rows, explicit comparison calls
     (lowered `ifOut`/`ifValue`), and explicit exports. Row increase is weighed
     against repair quality and friction logs, not treated as a standalone hard
     fail.
2. Edit-locality for the following operations must improve or stay neutral:
   insert a call, insert cleanup after an owned handle, add a branch guard,
   add an async fan-out.
3. Agent friction logs must not shift toward "mandatory row busywork" — the
   same category the project has already been reducing.

**Measurement plan.** Convert the most complex handler first (DB-reading,
error-branching, response-writing). Count before/after. Run the agent game on
the converted version and record friction categories. If gate 1 fails, narrow
metadata requirements further. If gate 3 fails, reassess which rows add cost
without structural value.

**Edit locality targets.**

| Operation | Expected v0.3 cost |
|---|---|
| Insert call between existing steps | 1 `do` row + 1 call entity block |
| Insert cleanup after owned handle | 1 `defer` row + 1 cleanup call block |
| Add branch guard for status check | 1 `branch ifOut`/`ifValue` row authored (canonical EAV expands it to a comparison call + `branch if`) |
| Add async fan-out | 1 `start` row per call; 1 `join` + `branch ifError` per result |

If any of these cost more than shown, activation wiring or type coupling has
accumulated extra cost — stop and assess before converting the rest.

---

## 22. Canonical block ordering

The formatter enforces a single canonical ordering. Agents producing EAV source
must emit rows in this order to guarantee stable diffs.

### File-level entity order

Each file type has a distinct legal entity set and ordering; the formatter
applies the order for the file's type and never moves an entity into a file where
it is not legal.

**Module source (`.sem`):**

```
1. module entity (path, imports, exports, metadata)
2. capability entities
3. alias entities
4. enum entities
5. record entities
6. error entities
7. errorCase entities
8. module-scope storage entities and DSL islands
9. webServer entity
10. operations (each followed immediately by its call, task, and cleanup blocks)
```

The `project` entity is **not** in module source — it lives in `build.sem` (§7).

**Manifest (`build.sem`):** exactly one `project` entity (rows ordered below),
followed by any `platform` entities in declaration order:

```
1. PROJECT is project
2. PROJECT module / target / entry / mode
3. PROJECT languageVersion / toolchain
4. PROJECT require ...          (one per dependency, by path)
5. PROJECT replace ...
6. PROJECT allowEffect ...
7. PROJECT nativeLibrary / nativeHeader / nativeLinkFlag   (§30.4.1)
8. PROJECT platform / constant / configure
9. platform entities (each: is, os, arch, targetRuntime, output, then
   per-platform nativeLibrary/nativeHeader/nativeLinkFlag, override, then metadata)
```

**Lock (`build.sem.lock`):** generated; one `project` entity carrying
`resolved` / `toolchainResolved` / `effectSurface` rows ordered by dependency
path. Never hand-ordered.

**Signature (`.semsig`):** `intrinsic` entities (plus the `record`/`enum`/
`alias`/`error` they reference), ordered by `target` path. No `operation`,
`webServer`, or `project` entities.

**Test (`.test.sem`):** module-source order, over a restricted entity set —
`tag test` operations and the helper `operation`s they call; their `call`/`task`/
`cleanup` blocks; `capability` entities (including test-double fakes, §30.5.2);
`record`/`enum`/`alias`/`error` and module `storage` used as fixtures; and
`imports`. **Not** legal in a `.test.sem`: `project`, `webServer`, `platform`, or
`intrinsic` entities. A `.test.sem` shares its sibling source file's module
(§30.5.1).

Within each group, entities appear in document-definition order (first
declaration wins); the formatter does not reorder within a group. Universal
metadata rows and the `forTarget`/`forPlatform`/`suppress` declaration predicates
(§30) sort **after** an entity's structural rows in every block.

### Operation-declaration row order

Within a single operation block:

```
OP is operation
OP in <param>...            (one per input, declaration order)
OP out <type>
OP effect <action> <res>... (one per effect)
OP uses <cap>...            (one per capability)
OP memory <dim> <val>...    (one per dimension)
OP async <yes|no>
OP body <steps|runtimeBinding TARGET|intrinsic NAME>   (default steps; omit when steps)
OP purpose "..."
OP invariant "..."...       (one or more)
OP rationale/risk/example/tag/deprecated/owner ...     (universal metadata, §6)
OP forTarget / forPlatform / suppress ...              (declaration predicates, §30)
OP export c <symbol>                                   (C export, §30.4.2)
OP label <name> <metaPred> <val>...  (label metadata rows)
OP let <name> <mut> <type>...        (let bindings, forward-ref order)
<step rows in execution order>
```

Followed immediately by the call, task, and cleanup blocks for this operation,
in the order their activation steps (`do`/`start`/`defer`) appear:

**Call block** (activated by `do`):
```
<callName> is call
<callName> in OP
<callName> invokes <target>
<callName> arg <slot> <type> <value>... (one per arg, declaration order)
<callName> out <var> <type>
<callName> catch <var> <type>
<callName> discards "..."
<callName> owns <var>
<callName> cleanedBy <cleanupName>
<callName> effect <act> <resource>
<callName> purpose "..."
<callName> risk "..."
```

**Task block** (activated by `start`):
```
<taskName> is task
<taskName> in OP
<taskName> invokes <target>
<taskName> arg <slot> <type> <value>... (one per arg, declaration order)
<taskName> out <var> <type>
<taskName> catch <var> <type>
<taskName> discards "..."
<taskName> owns <var>
<taskName> cleanedBy <cleanupName>
<taskName> effect <act> <resource>
<taskName> purpose "..."
<taskName> risk "..."
```

**Cleanup block** (activated by `defer`):
```
<cleanupName> is cleanup
<cleanupName> in OP
<cleanupName> call <callName>
<cleanupName> onFailure <policy>
<cleanupName> because "..."
<cleanupName> cleans <var>
<cleanupName> purpose "..."          (optional universal metadata; §6)
```

**Rationale.** Fixed ordering means a diff that adds a `memory` row never
touches the `invariant` rows. A diff that adds a `let` never touches `purpose`.
Agents can produce minimal diffs by knowing exactly which row slot to target.

---

## 23. Compact authoring profile

The compact profile is a first-class authoring syntax — not legacy syntax, not
informal shorthand. The formatter lowers it to canonical EAV on `sem fmt`.
Agents and humans may write either; canonical EAV is what the linter, query,
and explain tools operate on.

### Compact syntax rules

Within an `operation <name>` block, subject tokens are omitted. The operation
name is the implicit subject until the next subject header — `operation`,
`call`, or `task` — or the next top-level entity declaration. A `cleanup`
entity is not authored in compact form: the compound `defer CALL onFailure
POLICY because "..."` sugar stays in the operation block (the subject is
unchanged) and `sem fmt` generates the `cleanup` entity from it.

```sem
# capability is declared once, in canonical form — compact elides only the
# operation/call subject, not top-level entity declarations
stdoutWriter is capability
stdoutWriter grants write console.stdout

operation main
out ExitCode
effect write console.stdout using stdoutWriter
memory heap no
async no
purpose "Write hello world and return a process exit code"
invariant "All stdout writes go through stdoutWriter"
invariant "Returns writeFailedExitCode on any write failure"

let helloText immutable String "hello world"
let successExitCode immutable ExitCode 0
let writeFailedExitCode immutable ExitCode 1

do writeHello
ifError writeHello goto failed
return successExitCode

at failed return writeFailedExitCode

call writeHello console.writeLine
arg text String helloText
catch writeError ConsoleWriteError
purpose "Write the greeting text to stdout"
risk "May fail if stdout is closed or unavailable"
```

`effect write console.stdout using stdoutWriter` is a compact-profile
shorthand that declares the effect and the covering capability in one row;
the formatter expands it to `OP effect write console.stdout` + `OP uses CAP`.
The `using CAP` form does NOT auto-generate the capability entity or its
`grants` rows — the capability entity (`stdoutWriter is capability` + grants
rows) must already be declared separately in the source file. If the capability
does not exist, the linter reports an unknown entity.

`ifError CALL goto LABEL` is compact-profile shorthand for
`branch ifError CALL goto LABEL`. The subject and `branch` keyword are
inferred by context.

### Compact ↔ EAV equivalence

| Compact | Canonical EAV |
|---|---|
| `operation NAME` | `NAME is operation` |
| `call NAME TARGET` | `NAME is call` + `NAME in OP` + `NAME invokes TARGET` |
| `task NAME TARGET` | `NAME is task` + `NAME in OP` + `NAME invokes TARGET` |
| `call NAME TARGET` + `async yes` | `NAME is task` (promoted to task entity) |
| `defer CALL onFailure POLICY because "..."` | `CLEANUP is cleanup` entity + `OP defer CLEANUP` |
| `ifOut CALL cmp VAL goto LABEL` | comparison call + `OP branch if result goto LABEL` |
| `ifValue VAR cmp VAL goto LABEL` | comparison call + `OP branch if result goto LABEL` |
| `effect ACT RES using CAP` | `OP effect ACT RES` + `OP uses CAP` |
| `ifError CALL goto LABEL` | `OP branch ifError CALL goto LABEL` |
| `ifFalse VAR goto LABEL` | `OP branch ifFalse VAR goto LABEL` |

All other compact rows are identical to EAV rows with the subject omitted.

### What compact does not allow

- No multi-operation scope ambiguity: a `call` or `task` row resets the
  implicit subject until the next `operation`, `call`, or `task` header.
- No inlined step rows inside call/task blocks: `do`, `defer`, `start`, etc.
  remain in the operation block, not the call block.
- No omitted `is` rows: `operation NAME`, `call NAME TARGET`, and `task NAME
  TARGET` are the compact forms of the entity declaration, not the `is
  operation` / `is call` / `is task` rows.

### When to use compact vs EAV

Use **compact** when authoring by hand or when the operation is short and
self-contained. Use **EAV** when patching programmatically or when grep/diff
stability matters. `sem fmt --surface compact` emits compact; `sem fmt` emits
EAV.

---

## 24. Tooling commands

> **Spec status.** The commands in this section are **specification proposals**
> for the `sem` CLI. They define the target DevX contract — not a description of
> what is currently implemented. The current `sem` CLI **already implements**
> `fmt`, `check`, `lint`, `slice`, `graph`, `doctor`, `deps`, `test`, `explain`,
> `fix`, and `patch` — but with **code- and path-scoped argument shapes**, not the
> entity-scoped EAV forms shown here (today `explain` takes a diagnostic code,
> `graph`/`slice` take a path, `doctor` takes no `--op`). What is genuinely
> **proposed** (not yet implemented) is: the entity-scoped / `--for-edit`
> argument shapes; `fmt --surface`; and the new commands `query`, `trace`, `add`,
> `rename`, `normalize`, `pack`, `diff`, `verify-patch`, `scaffold`, `summarize`,
> `inventory`, and `lint --explain`. Each block notes whether it evolves an
> existing command's shape or is new; see the project roadmap.

`sem` is the SemanticScript CLI. All commands operate on the current project
unless a file path or entity name is given. All commands accept `--json` for
machine-readable output.

Together these form an **agent-safe operating environment** around the syntax,
not just a syntax: diagnose → slice → edit structurally → verify → summarize. The
highest-leverage loop is `sem doctor` → `sem slice --for-edit` → `sem add` →
`sem verify-patch` → `sem explain` (see "Agent-safe workflow" at the end of §24).

### `sem slice` — minimal task-specific context bundle

`sem slice` is the headline agent tool: it extracts a **minimal, complete**
context bundle for one edit or analysis instead of sending a whole file. (The
shipping CLI has a `sem slice`, but **path/operation-name-scoped with different
flags**; the entity-scoped `--for-edit`/`--with-cleanup`/`--path`/`--refs` surface
below is the **proposed** EAV evolution — spec-status banner above. Likewise
`sem test --lane` is proposed, §28.7.) Because
EAV is row-heavy and `call`/`task`/`cleanup` are explicit entities, the slicer
includes exactly the operation, bindings, types, capabilities, cleanup graph,
task graph, and errors an edit needs — and nothing else. The model is: canonical
EAV on disk → small semantic slices in prompts → stable cached spec/stdlib prefix
→ latest task at the prompt tail.

```bash
sem slice healthHandler                        # default slice
sem slice healthHandler --with-cleanup         # + ownership/cleanup graph
sem slice healthHandler --with-tasks           # + async lifecycle
sem slice healthHandler --path failed          # only rows on one control-flow path
sem slice healthHandler --refs db              # only rows defining/using/cleaning `db`
sem slice healthHandler --for-edit add-cleanup --producer openDb
sem slice healthHandler --format prompt|json|eav
```

**Output modes.** `--format prompt` emits stable, headed sections (below) for
direct LLM context; `--format json` emits a structured bundle
(`operation`/`declarations`/`bindings`/`steps`/`calls`/`tasks`/`cleanups`/
`types`/`errors`/`capabilities`/`effects`/`labels`/`paths`/`diagnostics`) for
programmatic patching; `--for-edit <kind>` patch mode adds the producer/cleanup
state, in-scope bindings, the suggested insertion point, and a canonical pattern
to follow.

**Default inclusion.** A bare slice includes the operation's declaration + `let`
+ step rows + label metadata, plus every `call`/`task`/`cleanup` it activates,
every capability named by `uses`, every error named by `catch`, every type named
by `in`/`out`/`arg`/`catch`/`let`, and the imports those external targets/types
need. Flags widen or narrow it:

| Flag | Adds / restricts |
|---|---|
| `--with-calls` | full call entity blocks referenced directly or indirectly |
| `--with-cleanup` | the `owns` → `cleanedBy` → cleanup-entity → worker-call ownership graph |
| `--with-tasks` | task entities + `start`/`join`/`poll`/`cancel`/`detach` steps + lifecycle diagnostics |
| `--path <label\|success\|failure>` | only rows reachable on that path, with live bindings + active defers |
| `--refs <name>` | only rows that define, use, clean, pass, mutate, or return `<name>` |
| `--for-edit <kind>` | `insert-call`/`add-cleanup`/`add-guard`/`add-task`/`fix-lint`/`rename` — producer/anchor/scope + canonical pattern |
| `--max-rows` / `--max-tokens` | budget caps; over-budget entities are summarized, never dropped silently |

**`--for-edit` examples.** `add-cleanup --producer openDb` returns `openDb owns
db`, the existing cleanup state, the `branch ifError` row, the correct `defer`
insertion point, and the canonical cleanup-entity pattern to emit. `add-guard
--after writeOk` returns the call output being guarded, in-scope comparison
values, and the canonical comparison-call + `branch if` pattern (canonical EAV
lowers `ifOut`, §13).

**Stable output sections** (prompt mode) — repeated headers act as prompt-cache
and attention anchors:

```
# Slice metadata        # Tasks            # Effects
# Operation declaration # Cleanups         # Labels
# Local bindings        # Types            # Diagnostics
# Step sequence         # Errors           # Suggested edit anchors
# Calls                 # Capabilities
```

**Agent contract.** A slice guarantees: (1) every included entity is complete
enough to patch; (2) every omitted entity is irrelevant or summarized; (3) every
binding used has its definition or source; (4) every external target has its
import/module context; (5) every label referenced has its definition; (6) every
included cleanup has its producer and worker call; (7) every included task has
its lifecycle steps. These guarantees are what make slices safe to hand an agent.

### `sem query` — semantic navigation

```bash
sem query entity main                # all rows for entity main
sem query kind operation             # all operation entity names
sem query kind call --in healthHandler  # calls declared in healthHandler
sem query effects --op healthHandler    # effects declared on healthHandler
sem query uses --op healthHandler       # capabilities used by healthHandler
sem query labels --op healthHandler     # labels defined in healthHandler
sem query cleanup --op healthHandler    # deferred cleanup entities in healthHandler
sem query async --unresolved            # started tasks with no join/cancel/detach
sem query refs helloText                # all rows that reference binding helloText
sem query types --ambiguous             # bare type names that match >1 import
sem query ownership --leaked            # owned bindings with no cleanup on some path
```

> **Current vs proposed shapes.** Several entity-scoped forms below differ from
> the shipping CLI, which is code-/path-scoped: today `sem explain` takes a
> diagnostic **code** (`sem explain SS1502`), `sem graph` takes a **path** with
> `--kind summary|routes` (`sem graph PATH --kind summary`), and `sem doctor`
> takes no `--op`. The entity-scoped forms here (`sem explain healthHandler`,
> `sem graph healthHandler --kind control`, `sem doctor --op healthHandler`) are
> the **proposed** EAV surface, not the current one (§24 spec-status banner).

### `sem explain` — human/agent-readable operation summary

```bash
sem explain healthHandler
```

Output:

```
healthHandler
  Inputs:   request HttpRequest, response HttpResponse
  Output:   Int32
  Effects:  readWrite database, write http.response
  Caps:     databaseAccess, responseWriter
  Memory:   heap no
  Async:    no

  Cleanup:
    closeDbCleanup  deferred after openDb success  (logAndSuppress)

  Failure paths:
    openDb failure       → failedNoDb  → writeFailNoDb  → return failNoDbResult
    readCount failure    → failed      → writeFail      → return failResult
    formatCount failure  → failed      → writeFail      → return failResult
    writeOk notEquals 0  → writeFailed                  → return writeResult

  Returns:
    success:    writeResult
    failed:     failResult
    failedNoDb: failNoDbResult
    writeFailed: writeResult
```

### `sem trace` — path simulation

```bash
sem trace healthHandler --path openDb:error
sem trace healthHandler --path success
sem trace healthHandler --path writeOk:notEquals
```

Output shows executed steps, live bindings at each step, registered defers,
and final return value. Useful for reasoning about goto-based control flow
without running the program.

### `sem graph` — control-flow and dependency graphs

```bash
sem graph healthHandler --kind control   # control-flow graph (CFG)
sem graph healthHandler --kind cleanup   # cleanup registration graph
sem graph healthHandler --kind async     # async lifecycle graph
sem graph healthHandler --kind effects   # effect and capability graph
```

Outputs Graphviz DOT by default; `--format mermaid` for Mermaid diagrams.

### `sem doctor` — repair-mode audit

```bash
sem doctor
sem doctor --op healthHandler
```

Groups output by severity and emits suggested `sem add` commands:

```
Critical:
  SS1502: openDb produces owned db; no closeDbCleanup defer is registered.
  SS1610: fetchUser started but not joined/canceled/detached before return.

Warnings:
  MD1021: private operation formatCount missing purpose.
  SS1012: label retry is unreferenced.

Suggested commands:
  sem add defer healthHandler closeDb --after openDb \
    --policy logAndSuppress --because "..."
  sem add join main fetchUser --after-start
```

### `sem add` / `sem rename` — structured edit commands

```bash
# Add a call entity and its activation step
sem add call healthHandler writeOk http.responseText \
  --arg response:HttpResponse=response \
  --arg status:HttpStatusCode=okStatus \
  --arg body:HttpTextBody=countText \
  --out writeResult:Int32

# Add a branch guard
sem add guard healthHandler \
  --ifOut writeOk notEquals successStatus --goto writeFailed

# Add a defer with placement hint
sem add defer healthHandler closeDb \
  --after openDb \
  --policy logAndSuppress \
  --because "database cleanup failure must not replace response status"

# Add an async join
sem add join main fetchUser --after-start

# Rename an entity
sem rename entity writeHello writeGreeting

# Rename a binding within an operation
sem rename binding healthHandler countText openCountText
```

`sem add` validates the operation signature before inserting. It will refuse to
add a call whose arg types do not match declared bindings.

### `sem normalize` — preview conversion

```bash
sem normalize --to eav --preview healthHandler
```

Output:

```
healthHandler
  Rows:
    current (compact): 42
    canonical (EAV):   54
    delta:             +12 (+28.6%)

  Edit-locality:
    insert call:    neutral
    add guard:      improved (was 3 rows, now 1)
    add cleanup:    improved (guard + defer = 2 rows)
```

### `sem task` — agent workflow templates

```bash
sem task add-route          # checklist for adding a webServer route + handler
sem task add-db-query       # checklist for a new sqlite query call
sem task add-cleanup        # checklist for deferring cleanup after an owned resource
sem task add-async-fanout   # checklist for start/join parallel calls
sem task convert-to-eav OP  # step-by-step codemod for one operation
```

Each emits a checklist of rows to add, rows to verify, and lint rules to check.

### `sem verify-patch` — pre-apply patch validation

```bash
sem verify-patch patch.sem
```

Validates a candidate agent patch before it touches the tree: all referenced
entities exist; all formatter-generated names are collision-free (§13, §15);
every ownership path closes (`owns` → `cleanedBy` → `defer`); every started task
resolves; return arity matches each operation's `out`; and `uses` capabilities
cover every effect in the union (§8). Pairs with `sem patch`: verify, then apply.

### `sem scaffold` — generate canonical patterns

Emits a whole canonical pattern so agents never hand-assemble malformed
multi-row constructs:

```bash
sem scaffold handler healthHandler --route GET /health
sem scaffold cleanup --producer openDb --worker closeDb
sem scaffold task fetchUser --target http.getJson
sem scaffold sqlite-query readCount
sem scaffold html-template taskRow
```

### `sem pack` — token-budgeted prompt packaging

```bash
sem pack healthHandler --task add-cleanup --budget 6000
```

Assembles a cache-friendly prompt: a stable **cached-prefix candidate** (only the
syntax rules + stdlib intrinsic signatures the task needs), then the **task
slice** (`sem slice --for-edit`), then **diagnostics**, then an **edit contract**
("produce patch only"). The direct answer to context slicing + prompt caching:
stable prefix cached, volatile task at the tail.

### `sem diff` — semantic diff

```bash
sem diff before.sem after.sem
```

Reports meaning-level changes — added cleanup, changed control flow, new/removed
effects or routes — not line noise. Built for agent review loops.

### `sem summarize` / `sem inventory` — module and project overviews

```bash
sem summarize taskWeb   # counts: exports, routes, capabilities, cleanups, unresolved tasks, lint
sem inventory           # project-wide: modules, exports, capabilities, owned resources + their cleanups
```

### `sem lint --explain` — diagnostic rationale

```bash
sem lint --explain SS1502
```

Explains why a rule exists and the canonical pattern that satisfies it. (The
shipping CLI's `sem explain <CODE>` is the current form of this.)

### Agent-safe workflow and build priority

The intended loop is **diagnose → slice → edit structurally → verify →
summarize**:

```bash
sem doctor healthHandler                       # 1. diagnose
sem slice healthHandler --for-edit add-cleanup # 2. minimal, complete context
sem add cleanup healthHandler --producer openDb --worker closeDb --policy logAndSuppress
sem verify-patch patch.sem                     # 4. prove it before applying
sem explain healthHandler                      # 5. confirm the new shape
```

Suggested build priority: `slice`, `explain`, `query`, `doctor`, `add`,
`normalize --preview`, `trace`, `graph`, `verify-patch`, `pack`; the rest layer
on once those exist. Several already ship (`slice`/`graph`/`doctor`/`explain`/
`deps`/`test`) in code-/path-scoped form — the work here is the entity-scoped EAV
shapes and the brand-new commands (spec-status banner above).

---

## 25. Formal scope model

### Binding sources

A name is in scope when it has been established by one of the following:

| Source | Binding name | Type | In scope from |
|---|---|---|---|
| Operation `in` row | the parameter name | declared type | first step |
| `let` declaration | the let name | declared type | first step (forward-ref rule §12 applies to initializers only) |
| Call `out` row | the out var name | declared type | after the activation step (`do`, `join`) |
| Call `catch` row | the catch var name | declared type | only on paths reached via `branch ifError CALL goto LABEL` |
| Module-level `storage` entity | the entity name | entity's `type` row | every step in every operation of the module (module-scoped global read) |
| Enum variants | bare variant name | the enum type | any type-directed position |
| Template holes | hole name inside `{{...}}` | String or HtmlSafeUrl | inside the island body only |

Module-level storage entities are in scope for reading in any operation's arg
and let positions — they are module globals. Writing them (via `out` targeting
the entity name) requires the `effect write storage.<name>` + capability model
(§12).

### Path-sensitive scope rules

**`out` bindings from sync calls.** After `OP do CALL`, the var declared by
`CALL out VAR TYPE` is in scope for all subsequent steps on the same path,
provided the operation does not `branch ifError CALL goto LABEL` (if it does,
the out var is only valid on the non-error path — the taken path jumped away).

**`out` bindings from async calls.** After `OP join CALL`, the var declared by
`CALL out VAR TYPE` is in scope. Before `join`, the var is not accessible.
`poll` alone does not bring out vars into scope.

**`catch` bindings.** `CALL catch VAR TYPE` is in scope only at label targets
of `branch ifError CALL goto LABEL` rows in the same operation. The catch var
is not in scope on the non-error path.

**Shared catch variables.** When multiple calls share the same `catch` var name
(shared error pattern, §15), the linter tracks which call most recently
produced it. At a shared failure label, the var is in scope from any of the
contributing calls. The linter warns if the catch type is not compatible across
all contributing calls.

**Label scope.** A label defined by `OP at LABEL STEP` is in scope as a `goto`
target for all step rows in the same operation. Labels are not hierarchical —
any step can jump to any label in the same operation.

**Let binding forward-reference.** A `let` initializer may only
reference names already in scope by document order (§12). The binding itself
is in scope from the first step row, not from its position in document order.

### Lint checks derived from scope

- `branch ifError CALL` where `CALL` has no `catch` row: hard error (catch var
  would be unbound at the target label).
- Reference to `out` var before `do CALL` or `join CALL`: hard error (unbound).
- Reference to `catch` var outside an `ifError` target path: hard error.
- `join CALL` before `start CALL` on all reachable paths: hard error (call not started).

---

## 26. Stdlib signature format and ownership

The linter must know whether a target returns void, can fail, owns resources,
is async, or has trust constraints. This knowledge lives in stdlib signature
declarations, not in user source.

### Intrinsic signature format

```sem
sqliteOpenDatabase is intrinsic
sqliteOpenDatabase target sqlite.openDatabase
sqliteOpenDatabase arg path String
sqliteOpenDatabase arg mode SqliteOpenMode
sqliteOpenDatabase out db SqliteDatabase
sqliteOpenDatabase catch SqliteDatabaseOpenFailure
sqliteOpenDatabase owns db cleanedBy sqlite.closeDatabase
```

`is intrinsic` declares a stdlib-defined signature. The `target` is the
external path (same as `invokes` in user source). `arg` rows declare positional
arg types (slot names are documentation only for the signature).

**Intrinsic `catch` grammar.** In intrinsic signature rows, `catch` takes a
type only (no variable name): `NAME catch ErrorType`. This differs from call
entity syntax where the programmer supplies the variable name:
`callName catch openErr SqliteDatabaseOpenFailure`. The variable name is
user-chosen in the call entity; the intrinsic signature declares only the error
type. `out` rows in intrinsic signatures similarly use `out VARNAME TYPE` where
`VARNAME` is a documentation-only slot name.

**`http.callNext` intrinsic:**

```sem
httpCallNext is intrinsic
httpCallNext target http.callNext
httpCallNext arg next NextMiddleware
httpCallNext out continued Bool
```

The `continued Bool` output is the return value of the downstream middleware
chain. The middleware returns it directly or checks it before returning its own
`out Bool`.

### Ownership annotation

`owns VAR cleanedBy TARGET` declares that the `out` var is an owned resource:
- The caller is responsible for releasing the value via `TARGET` before the
  owning operation exits on any success path.
- The linter generates SS1502 if a `cleanup` entity wrapping `TARGET` is not
  registered (via `defer`) on every path where the owned var is live at exit.

**`cleanedBy` referent differs by entity kind.** In an `intrinsic` signature,
`cleanedBy <TARGET>` names the cleanup *target function* (an external path such
as `sqlite.closeDatabase`); a signature cannot reference a user entity. In a
user `call`/`task` (§15), `cleanedBy <NAME>` names the cleanup *entity* (§15.6)
that wraps that target (such as `closeDbCleanup`). The intrinsic states which
function releases the resource; the call states which registered cleanup runs it.

Multiple `owns` rows are allowed for calls that produce multiple owned values.

### Trust and context annotations

```sem
htmlRender is intrinsic
htmlRender target html.render
htmlRender arg template HtmlTemplate
htmlRender arg ...
htmlRender out HtmlFragment
htmlRender trustConstraint arg body HtmlSafeUrl  # arg slot must receive HtmlSafeUrl
```

`trustConstraint arg SLOT TYPE` declares that if the template contains a
URL-bearing hole bound to SLOT, the arg must supply `HtmlSafeUrl`. This is how
the linter enforces §16's HtmlSafeUrl rule without requiring the template to
declare it.

**General rule.** `trustConstraint` declares a non-type precondition that must
hold before a trust-sensitive output (such as `HtmlSafeUrl` or
`HtmlTrustedFragment`) is produced. Two forms: `trustConstraint arg SLOT TYPE`
(the named arg slot must carry the trusted type) and `trustConstraint NAME` (a
named, documented sanitization precondition, e.g. `sanitizedInput`). It is valid
only on `intrinsic` entities, and the linter enforces it only when the producing
call's `target` resolves to a known intrinsic; for unknown targets it is
documentation. User-defined `trustConstraint`s are advisory in v0.3.

```sem
htmlTrustFragment is intrinsic
htmlTrustFragment target html.trustFragment
htmlTrustFragment arg input String
htmlTrustFragment out trusted HtmlTrustedFragment
htmlTrustFragment trustConstraint sanitizedInput
```

Here `trustConstraint sanitizedInput` records that the `String` passed to
`html.trustFragment` must already be sanitized before the call produces an
`HtmlTrustedFragment` (§16). `sanitizedInput` is a documented precondition, not
a type the linter can prove — so for this stdlib intrinsic the linter surfaces
the constraint, but it cannot statically verify that the input was sanitized.

### Typed trust/taint flow (X-070, §16/§26)

A type carries a **trust label** with `typeTrust`:

```sem
RawBody is alias
RawBody for String
RawBody typeTrust rawExternal        # untrusted input (e.g. an HTTP body)

SafeSql is alias
SafeSql for String
SafeSql typeTrust validated          # trusted only after a validation boundary
```

The labels are `rawExternal | validated | trustedInternal | secret`. Untrusted
input enters as `rawExternal` and becomes trusted only by crossing a declared
trust boundary — a validator whose **output** type is `validated`/
`trustedInternal`. An operation marks a trust-sensitive **sink** parameter with
`trustConstraint arg <slot>`; passing a value whose declared type is
`rawExternal` (or `secret`) into that slot is a hard error (**SS3070**):

```sem
runQuery is operation
runQuery in sql SafeSql
runQuery trustConstraint arg sql     # this slot must receive trusted input
```

Because trust is a property of the value's declared type, it propagates over the
explicit `out`→`arg` dataflow with no aliasing — so the check is exact, not
heuristic. (This promotes `trustConstraint` from advisory to enforced when the
arg type carries a trust label.)

**Sink-typing (X-071).** When a sink names the trusted type it requires —
`trustConstraint arg <slot> <TrustedType>` (SQL→`SqlText`, HTML→`HtmlSafeUrl`,
path→`SafePath`, …) — the arg must *be* that trusted type, or a
`validated`/`trustedInternal`-labeled type. A plain `String` is rejected
(**SS3071**), and a value assembled by `string.concat` may **never** reach a sink
(no string-built queries/markup, §30.2.2) — you build the trusted type at a
boundary, never by concatenation:

```sem
sqlExec trustConstraint arg sql SqlText   # the SQL sink requires SqlText
# runSql arg sql String rawText           -> SS3071 (plain String)
# runSql arg sql SqlText concatResult     -> SS3071 (string-built)
# runSql arg sql SqlText validatedQuery   -> ok
```

**Secret-typed values (X-072).** A `typeTrust secret` value is *usable*
(verify/sign/TLS) but never *observable*. Writing a secret to an observable sink
(console/`log.*`) is a hard error (**SS3072**), and a secret-typed binding may
not be initialized from a source literal — no hardcoded secrets; load them from a
capability-gated source. Because a secret can never reach an observable or
transcript sink, there is nothing to leak into a `capturedOutputReplay`
transcript: the compile-time block is stronger than runtime redaction.

**Constant-time secret comparison (X-074).** Comparing a secret with a
`math.*`/`compare.*` equality leaks via timing — a hard error (**SS3074**).
Secrets compare only through `crypto.equalConstantTime`.

**Bounded untrusted decoding (X-077).** A decode of a `rawExternal` input
(`json.parse`/`json.decode`/`json.createDocument`/`codec.decode`) must carry a
`limit maximumBytes <n>` row so malformed/hostile input cannot exhaust memory; an
unbounded untrusted decode is a hard error (**SS3077**, deserialization-DoS
defense):

```sem
decode invokes json.parse
decode arg text RawJson body          # body is typeTrust rawExternal
decode limit maximumBytes 65536       # required for untrusted input
```

**CSPRNG vs deterministic RNG (X-073).** Security material (keys/tokens/nonces/
salts) must be drawn from the CSPRNG (`random.entropy`). A value drawn from a
seeded/deterministic RNG (`random.deterministic`, …) that flows into a security
generator (`crypto.generateToken`/`generateNonce`/`generateSalt`/`generateKey`/
`randomBytes`) is a hard error (**SS3073**); the seeded RNG stays valid for
reproducible non-security use. A nonce/IV is affine — consuming one
(`crypto.generateNonce`/`generateIv` output) in two cryptographic calls is a
nonce-reuse error (also SS3073).

**Path-traversal-safe filesystem (X-076).** A filesystem path is confined under a
root. An `fs.*` path argument that is a literal containing a `..` segment or an
absolute root is a hard error (**SS3076**); confine paths with `fs.resolveWithin
<root>` (which yields a `SafePath`), and raw-String paths into a `SafePath` sink
are caught by sink-typing (SS3071).

**Host-scoped network / SSRF (X-075).** An outbound `net.*`/`http.*` request URL
literal that targets localhost, a private/link-local range, or the cloud-metadata
address (`169.254.169.254`) is a hard error (**SS3075**); requests go to
allowlisted external hosts via an `HttpSafeUrl` (raw-String URLs are caught by
sink-typing). The per-host allowlist rides the net capability at runtime.

**DoS bounds (X-078).** An effectful external call
(`net.*`/`http.*`/`sqlite.*`/`db.*`/`fs.*`) that takes a `rawExternal` argument
must carry a `timeout` or `budget` row, so a slow/hostile peer cannot stall the
process; an unbounded untrusted external call is a hard error (**SS3078**). (The
untrusted-decode size cap is X-077's `limit maximumBytes`.)

**Error-disclosure boundary (X-079).** An internal error/trap detail
(`typeTrust trustedInternal` on the error type) may not reach a client-response
sink (a `clientResponse arg <slot>` parameter) without an explicit
`errorBoundary <InternalError> <ClientError>` mapping on the calling op;
returning a raw internal error to a client is an information-disclosure hard
error (**SS3079**).

**UTF-8 boundary validation (X-096).** Bytes become text only through a
validator. A bytes→text decode (`bytes.toText`/`string.fromBytes`/
`text.fromUtf8`/…) of a `rawExternal` source must bind its result to a
`validated`/`trustedInternal` text type — decoding untrusted bytes straight into a
plain `String` is a hard error (**SS3096**), so invalid UTF-8 cannot silently
corrupt an internal string.

**Secure-by-default opt-out (X-080).** Security is on by default (auto-escape,
secure cookies, CSRF, host allowlist). Weakening any of it is an explicit,
justified row — `optOut <protection> because "…"`; an opt-out with no `because`
is a hard error (**SS3080**), so every weakened default stays greppable and
accountable. (The default cookie/header/CSRF *builders* live in the deferred web
stdlib.)

### Async intrinsics

```sem
httpGetJson is intrinsic
httpGetJson target http.getJson
httpGetJson async yes
httpGetJson arg url String
httpGetJson out user User
httpGetJson catch HttpError
```

`async yes` on an intrinsic means user source must use `start`/`join`, not
`do`. Matches the call entity's `async yes` declaration requirement.

### Where signatures live

`intrinsic` entities are stdlib/toolchain **signature metadata**, not normal
application declarations. Application modules reference intrinsic *targets*
through `imports` + `invokes`; they should not declare `is intrinsic` entities
themselves. An `is intrinsic` row in an application module is a lint warning
("intrinsic signatures belong in a `.semsig` file, not app source"), so an agent
cannot silence a missing-signature lint by hand-declaring a fake signature.

Stdlib signatures are compiled into the toolchain. Third-party libraries ship a
`.semsig` sidecar declaring their signatures in the same EAV format:

```sem
# file: company.api.semsig
companyApiFetchUser is intrinsic
companyApiFetchUser target api.fetchUser
companyApiFetchUser async yes
companyApiFetchUser arg userId String
companyApiFetchUser out user User
companyApiFetchUser catch ApiRequestError
```

A `.semsig` file contains only `intrinsic` entities plus the
`record`/`enum`/`alias`/`error` declarations its signatures reference, one file
per module path, named `<module.path>.semsig`. **Resolution.** Before checking a
module, the linter collects `.semsig` files in order from: an explicit
`--semsig-path`, then each imported module's package directory on the import
path, then the toolchain's bundled stdlib signatures. The first signature found
for a given `target` wins. Within a `.semsig` file, intrinsic entities are
ordered by `target` path (§22).

**Versioning.** A `.semsig` begins with a `semsig` **header entity**, so the file
stays pure EAV (entity + facts, no bare rows):

```sem
companyApiSig is semsig
companyApiSig version 1
companyApiSig generatedBy "sem1.0"
companyApiSig describes company.api
```

`version` is the schema version, `generatedBy` the emitting toolchain, and
`describes` the module path the signatures cover. The linter rejects a `.semsig`
whose `version` it does not understand rather than mis-reading it. The full
versioned field schema — which predicates are valid at each version, and the
compatibility policy — is roadmap (§29 #9); v0.3 fixes only this header entity and
the entity set above.

---

## 27. Out of scope for v0.3

The following constructs exist in the current project or have been requested
but are **not specified in v0.3**. They fall into three dispositions, and every
deferred *language* feature below carries a **v0.3 interim** (how to cope today)
and a **planned shape** (the direction, so v0.3 does not box it in):

- **Deferred language features** — need future *syntax* (collections, generics,
  loops, `match`, concurrency primitives, retry/timeout, FFI ABI, route
  params/policy).
- **External surface** — full stdlib APIs and system/GUI/codec libraries that are
  intentionally *outside* the core language spec (minimal core, logic in stdlib);
  reached through the existing capability/effect (§8) and `.semsig` (§26) hooks.
  See "External surface" below.
- **Already specified or resolved elsewhere** — cross-referenced to the owning
  section (e.g. build/deps → §28, value construction → §10.5, data inspection →
  §13 `ifVariant`). A few deferred items (`staticRoute` static-file serving,
  `standard.document`/wasm DOM, pointer-backed `OpaquePointer`/`FileHandle`) are
  **implemented in the current toolchain today** and EAV defers them — existing
  code using them is a corpus-migration concern (§29 #17), not fresh design.

**v0.3 scope note.** This feature set is sufficient for the worked-example class
— console programs, static-route web handlers, sqlite access, HTML rendering —
but **not** for programs needing dynamic collections, iteration over
runtime-sized data, generics, or true parallelism until the deferred features
land.

### Intentionally deferred (planned for a future version)

**Route parameters and wildcards.** Dynamic routing (`:id`, `*`) is not in
v0.3. Only exact-match static routes. Decision point: a v0.4 route spec would
add `route GET "/tasks/:id" handler` with `:id` as a typed arg binding.

**`standard.document` and wasm DOM.** The `wasm` target exists but its
document/DOM interaction model (`standard.document`, wasm DOM APIs, JS
interop) is not specified in v0.3. `target wasm` currently means an operation
exported to a wasm host; host communication beyond return values is runtime-
and host-defined.

**FFI / native interop and role/opaque types** (`OpaquePointer`, `FileHandle`,
`ByteCount`, time aliases like `UnixTimestamp`, `Duration`, `Milliseconds`,
native source/link args, and similar ABI-role wrappers). These are stdlib-defined
`alias` types, not additional primitives.
- *Interim (v0.3):* drop to a primitive with `operation body runtimeBinding
  <target>` / `body intrinsic <name>` (§11) and declare the foreign signature as
  an `intrinsic` in a `.semsig` (§26). Treat `OpaquePointer` as `UInt64` until the
  FFI spec lands. These hooks already exist; only the ABI-role *type catalog* and
  native link/source declarations are missing.
- *Planned:* a `standard.ffi` module supplying the ABI-role aliases, plus
  `native` link/source declarations attached to the build manifest (§28), not to
  source rows.

**Structured loops.** No `loop`, `while`, `each`, `break`, `continue`.
- *Interim (v0.3):* the documented label/`goto` patterns — top-tested `while`
  and bounded-counter retry (§13). Complete for fixed iteration; what hurts is
  iterating a runtime-sized collection (see *Collections*).
- *Planned:* `repeat`/`each` as **non-canonical sugar** (like `ifOut`, §13) that
  `sem fmt` lowers to labeled gotos with deterministic label names — not a new
  block construct, since the tape has no block delimiters. `each ITEM in COLL`
  pairs with the collection model below; `break`/`continue` lower to `goto` of the
  generated loop-exit / loop-head labels.

**Generics / type parameters.** `Result OK ERR` is the only parameterized form
in v0.3; user records/enums and stdlib types may not take type parameters.
- *Interim (v0.3):* monomorphize by hand — declare concrete types (`TaskList`,
  `UserList`) or use opaque stdlib handles whose element type is fixed by the
  producing call's signature.
- *Planned:* a `typeParam` declaration row plus the bracket-free application form
  already used by `Result` — `Box typeParam T`, then `Box field value T`, used as
  `Box of Task`. No `<...>` angle syntax (consistent with no-symbols); variance
  and constraints are a later increment.

**Concurrency primitives.** Channels, mutexes, select, task groups, intervals,
worker pools, and wait-sets are not in v0.3.
- *Interim (v0.3):* the cooperative `task` lifecycle — `start`/`join`/`poll`/
  `cancel`/`detach` (§13) — on the single-thread backend (fan-out-shaped but
  sequential; §13 backend semantics). Shared state uses module `storage` with the
  `effect write storage.<name>` + capability model (§12), race-free under the
  single-thread backend.
- *Planned:* new entity kinds (`channel`, `mutex`, `taskGroup`, `interval`,
  `workerPool`) in a `standard.concurrent` module, gated on a concurrent backend
  (v0.5+). They reuse the entity/predicate row model, not new operators.

**Collections (lists, arrays, maps).** `listType`/`arrayType`/`sliceType`/
`mapType`, collection literals, indexing, and iteration contracts are not in
v0.3. This is the sharpest expressiveness limit: v0.3 has no first-class way to
hold a runtime-sized set of values.
- *Interim (v0.3):* a collection is an **opaque handle** returned by a stdlib
  module (e.g. a `standard.list`/`standard.map` `List`/`Map` type) operated on by
  calls (`list.append`, `list.get`, `list.length`); a result set is consumed by a
  top-tested `goto` loop reading one item per iteration (the sqlite `stepResult`
  pattern in §16/§19 is exactly this). Small fixed groups can be a `record`. There
  are no collection literals or indexing syntax — every access is a call.
- *Planned:* parameterized stdlib types (`List of T`, `Map of K V` — the `of` row
  form, no angle brackets) plus the `each` loop sugar above. Iteration and
  ownership follow the same `owns`/`cleanedBy` model as other resources.

**Retry, timeout, cancellation policy.** `retryPolicy`, `useRetry`, `timeout`,
`timeoutBudget`, `cancelOn` are not in v0.3.
- *Interim (v0.3):* bounded-counter `goto` retry (§13 retry example); timeout
  modeled as a concurrent timer `task` raced against the work (§13 timeout
  example); cancellation via `cancel TASK` (§13).
- *Planned:* declaration rows attached to a `call`/`task` — `useRetry POLICY`,
  `timeout BUDGET`, `cancelOn TOKEN` — with a `retryPolicy` entity (max attempts,
  backoff). They lower to the goto/timer patterns, so the policy stays
  declarative source data rather than hand-rolled control flow.

**GUI target.** `windowsGui` is reserved; `standard.gui`, `guiBackend`, and
Win32 native bridge support are not in v0.3. `target windowsGui` is a compile
error until a GUI spec is approved.

**Route policy rows.** `routeTimeout`, `routeTimeoutOptOut`,
`routeMiddlewareOptOut` are not in v0.3.

**HTTP surface details.** Static-file serving (the current `staticRoute`
prefix/directory feature), redirect helpers, cookie/header bindings, SSE,
null-body handling, response-body/SQL forwarder declarations, and request
readers beyond `HttpRequest` are not in v0.3. These are stdlib patterns, not
syntax.

**Fine-grained import rows.** `importOperation`, `importType`, `importError`,
`importCapability`, `importConstant` are not in v0.3. `imports ALIAS PATH`
imports the whole module; fine-grained selective imports are a future syntax.

**Build and package metadata.** The core build and dependency model **is**
specified — `build.sem` (identity, `languageVersion`/`toolchain`,
`require`/`replace`, targets) and the generated `build.sem.lock` (§28). What is
deferred is the *vanity/packaging surface*: `publisher`, `productName`, build
profiles, explicit output paths, and icon/resource rows. These live in the
`build.sem` manifest (the toolchain config layer), never in module source rows,
and are added incrementally without touching the language grammar.

**Data-carrying destructuring / `match` — RESOLVED (§13 `ifVariant`).** Earlier
drafts deferred this; v0.3 now inspects data-carrying enum variants and error
cases with the canonical `branch ifVariant VALUE VARIANT bind PAYLOAD goto LABEL`
guard (§13): it narrows to a known variant and binds its payload on the taken
path (catch-style scope), and a series of `ifVariant` rows over one value is the
match, with exhaustiveness linted (§17 #52). Records are read with
`<Record>.<field>` (§10.5); payloadless enums also support `equals`/`notEquals`.
There is no `match` *block* — inspection reuses `branch`/`goto`, so the flat tape
is preserved. (A multi-arm `match` *sugar* that lowers to `ifVariant` rows
remains possible future ergonomics, but is not required for expressiveness.)

### External surface (stdlib & ecosystem — outside the core spec by design)

The core language is deliberately small; substantial functionality is library
surface, not grammar. These are not "missing" from the language so much as
**owned by stdlib modules** and reached through the language's existing hooks:
capabilities + effects (§8) for authority, `intrinsic` signatures + `.semsig`
(§26) for contracts, and per-module generated docs for catalogs.

**Full stdlib API catalogs.** The spec names modules (`standard.http`,
`standard.sqlite`, `standard.html`, `standard.convert`, …) and their key types
but does not enumerate every operation, error contract, or type. By design: each
module's complete API is its `.semsig` (§26) plus generated docs, versioned with
the module (§28.4/§28.6) and queried with `sem docs`. The language spec fixes the
*contract shape*, not the catalog.

**System APIs** — filesystem, process, environment, clock, random, network
clients. Not yet shipped as stdlib modules, but they need **no new language
feature**: each is a `standard.*` module whose targets are capability-gated
effects (e.g. `effect read filesystem.path` + a covering capability, §8) with
`.semsig` signatures. Planned namespaces: `standard.fs`, `standard.process`,
`standard.environment`, `standard.clock`, `standard.random`, `standard.net`.
Until they ship, only the targets already used in examples (`console.*`,
`sqlite.*`, `http.*`, `html.*`, `convert.*`, `compare.*`) are available.

**GUI, browser DOM, and JSON codecs** (the `standard.gui`/`windowsGui`,
`standard.document`/wasm-DOM, and JSON-codec/validation items) share this
disposition: stdlib plus target-ABI work, gated behind the capability/effect and
`.semsig` model and specified when their modules are. JSON in particular is an
application pattern over a future `standard.json` module (§16), not core syntax;
record JSON metadata (`jsonName`/`omitWhen`) lands with that module's spec.

### Mapped by existing v0.3 constructs

**`call async yes` and compound `defer`).** Both are deprecated compact sugar
forms in v0.3:
- `call NAME TARGET` + `NAME async yes` → `NAME is task` entity. `sem fmt`
  promotes the call to a task entity automatically. The `async` predicate is
  not valid on a `call` entity in canonical EAV.
- `OP defer CALL onFailure POLICY because "..."` (compound inline defer) →
  `CLEANUP is cleanup` entity + `OP defer CLEANUP`. `sem fmt` generates the
  cleanup entity. The compound form is non-canonical sugar only; it does not
  appear in strict canonical EAV output.

**MiddlewareControl enum vs Bool.** v0.3 uses `out Bool` for middleware (§14).
If the current project uses a `MiddlewareControl` enum, map `continue` →
`true`, `stop` → `false` in v0.3 source. A future version may restore the
enum contract if middleware needs richer signaling.

**`makeError` / `declareFailure`.** Error value construction is performed by a
call to the built-in `<Error>.<case>` target (§10.5), whose `out` is the error
type and whose `arg` is the case payload (if the case declares one). There is no
separate `makeError` syntax in v0.3.

**Type metadata rows** (`typeInvariant`, `typeRepresentation`, `typeTrust`,
`typeMemory`, `typeLayout`, etc.). These map to metadata rows on the type
entity: `TYPE invariant "..."`, `TYPE note "..."`, etc. (§6). The v0.1
type-prefixed names are obsolete.

**Record executable rows** (`new`, `fieldSet`, `fieldGet`, `recordConstructor`,
etc.). These map to calls on the built-in `<Record>.new` (construct) and
`<Record>.<field>` (read) targets (§10.5). There is no in-source record
constructor *syntax* — construction is a typed call. Whole-record update is
`<Record>.new` returning a fresh value, rebound through a `let mutable` `out`
(§12); fields are not individually mutable.

**Record JSON metadata** (`recordFieldJsonName`, `recordFieldJsonOmitWhen`,
etc.). Deferred to the JSON codec spec. Do not use `fieldJsonName` or similar
predicates in v0.3 source — the exact predicate names are not yet stable and
will be specified when the `standard.json` module API is defined.

**Domain/static literal structures** (`domainLiteral*`, `literalSource`,
`literalBytes`, etc.). Map to `storage` entities with `body` islands.
`literalSource` asset loading is a compiler directive expressed as a `storage`
entity with a `body` island. Note: `alias` entities do not support a `value`
predicate — aliases declare only their base type via `for`. Static values must
use `storage` entities, not aliases.

**`section` and `group` retrieval/context structures.** Map to module-level
`storage` or `record` entities grouping related values. No `section` or `group`
keyword in v0.3.

**Dependency/resource structures** (`dependency*`, `resource*`,
`dependencyFunction*`). Map to `capability` entities with `grants` rows and
`imports` rows. The full dependency metadata schema is a build-system concern.

**Codec/validator/boundary/policy structures.** These are stdlib patterns
invoked via call entities. No syntax-level codec primitives in v0.3.

**Runtime/interop structures** (`operationBody`, `runtimeBinding*`,
`intrinsicName`, `nativeRuntimeSource`, `nativeRuntimeLinkArg`, etc.). Map
to `is intrinsic` signature declarations (§26) or `runtimeBinding` operation
declarations. No change to source syntax.

**`observability`, `timing`, `security`, `testCovers`, `precondition`,
`guarantee`, `failure`, `warning` metadata.** Map to universal metadata rows
(`note`, `risk`, `invariant`, `tag`) in v0.3. Specialized metadata predicates
may be added in a future metadata expansion.

---

## 28. Project structure, modules, and packaging

This section specifies the **toolchain config layer** that §27 ("Build and
package metadata") defers to — the project and packaging framework, not new
source syntax. It builds on the module model in §7.

The model is deliberately Go-shaped, for the same reasons Go chose it:

- Import paths are repository paths. There is no central registry.
- Dependency versions live in a manifest, **never in `imports` rows**, so a
  version bump never touches source and never breaks grep-locality.
- Resolution is reproducible by Minimal Version Selection (MVS), not a SAT
  solver — simpler to implement and far more legible to an agent.
- Integrity is content-addressed (sha256), reusing the digest primitive the
  language already has (`literalDigest`, §10-era metadata).

What it adds beyond Go: because effects and capabilities are first-class
(§8), a dependency's entire effect surface is declared data, so the resolver
can enforce a supply-chain capability contract at resolve/link time (§28.5) —
a guarantee npm, cargo, and Go cannot make.

### 28.1 The two project files

A buildable project root holds exactly two packaging files. Both are
SemanticScript data — same parser, same `sem query` surface — so there is no
second config format (no TOML, YAML, or JSON manifest) to learn.

| File | Authored by | Committed | Holds |
|---|---|---|---|
| `build.sem` | human/agent | yes | identity, language + toolchain version, `require`/`replace` deps, build targets, platforms, constants |
| `build.sem.lock` | `sem` (generated) | yes | resolved dep graph (path → version → sha256), aggregated capability surface, resolved toolchain version |

`build.sem` absorbs what Go splits across `go.mod` plus build configuration; it
is the evolution of the existing build-plan record data, with dependency rows
added.

`build.sem.lock` is generated and **never hand-edited**. The `.sem.lock` suffix
marks a generated, read-only artifact: the toolchain parses `*.sem.lock` as
ordinary SemanticScript (so it stays typed, lintable, and queryable) but refuses
hand edits and regenerates it with `sem mod tidy`. Only the **main module's**
lock is authoritative for a build; dependency locks are ignored — MVS reads each
dependency's `require` rows, not its lock (Go's rule).

`build.sem` dependency rows:

```sem
# language and toolchain pinning — the compiler refuses a mismatch rather
# than miscompiling
TaskApp languageVersion "1.0"
TaskApp toolchain "sem1.0"

# version pins live here, not in source imports rows
TaskApp require sqlite github.com/ss-lang/sqlite v1.4.0
TaskApp require markdown github.com/foo/markdown v2.1.0

# local multi-repo development — redirect a dep to a path on disk
TaskApp replace github.com/ss-lang/sqlite "../sqlite"
```

The matching source `imports` row carries the alias and path but no version
(§7): `taskWeb imports sqlite github.com/ss-lang/sqlite`.

**Full `build.sem` row grammar** (all rows are predicates on the `project`
entity, §5; one record per row):

```
PROJECT is project
PROJECT module <moduleName>               # the project's root module
PROJECT target <console|webServer|wasm>   # one row per built target
PROJECT entry <operation|webServer>       # the entry entity (§7); repeat per target, gating the named entity with forTarget
PROJECT mode capturedOutputReplay         # optional determinism mode (§30.1.1)
PROJECT languageVersion "<x.y>"           # language pin
PROJECT toolchain "<id>"                  # toolchain pin
PROJECT require <alias> <path> <version>  # one row per dependency
PROJECT replace <path> "<localPath>"      # dev/override redirect
PROJECT allowEffect <action> <resource>   # supply-chain capability allowlist (§28.5)
PROJECT platform <name>                   # references a platform entity (§28.1)
PROJECT constant <name> <type> <value>    # build-time constant (project-global, §28.1)
PROJECT configure <operationName>         # build-time op → out BuildPlan (§30.3.2)
PROJECT nativeLibrary <name>              # native link inputs (§30.4.1)
PROJECT nativeHeader "<path>"
PROJECT nativeLinkFlag "<flag>"
```

**`build.sem.lock` row grammar** (generated, never hand-edited):

```
PROJECT is project                                  # the lock re-anchors the project subject (every entity's first row is `is`)
PROJECT resolved <path> <version> sha256 <digest>   # one row per resolved dependency
PROJECT toolchainResolved "<id>"                     # the locked toolchain
PROJECT effectSurface <path> <action> <resource>     # aggregated capability surface
```

Like every build row, lock rows are subject-anchored EAV — predicates on the
`project` entity, not verb-led records. The lock is parsed as ordinary EAV
(typed, lintable, queryable), but `sem` refuses hand edits and regenerates it
(`sem mod tidy`, proposed — §28.4).

**Platform entities (§28.1).** `PROJECT platform <name>` references a `platform`
entity declared in `build.sem` — not a bare string — so OS/arch/runtime/output are
structured data:

```sem
linuxAmd64 is platform
linuxAmd64 os linux                  # linux | macos | windows | wasi
linuxAmd64 arch amd64                # amd64 | arm64 | wasm32
linuxAmd64 targetRuntime native      # native | wasm
linuxAmd64 output "dist/app-linux-amd64"
linuxAmd64 override featureFlag false # per-platform build-constant override
```

A `platform` with no rows defaults to the host triple. `override <name> <value>`
shadows a `PROJECT constant` for that platform only: `<name>` must be a declared
`PROJECT constant` (unknown name is a hard error) and `<value>` must match that
constant's declared type (type mismatch is a hard error). A platform may also
carry its own `nativeLibrary`/`nativeHeader`/`nativeLinkFlag` rows (§30.4.1).

**Native-link merge.** For a built platform, native-link inputs are the
project-level rows (document order) followed by that platform's rows (document
order). Exact duplicates — same library name, same header path, same flag string
— are deduplicated to the first occurrence; otherwise `nativeLinkFlag` order is
preserved (linker flags are order-sensitive). Library names carry no version, so
there is no version conflict; reconciling two header paths is the author's
responsibility (the resolver does not reorder).

**Build constants (§28.1).** `PROJECT constant <name> <type> <value>` declares a
**project-global, read-only** build-time value. It is visible by bare name in any
module — resolved like a module-scoped `storage` global (§25) — and a local
binding of the same name is a hard error (no shadowing). This project-global
visibility is a **deliberate, named exception** to the import/export model (§7):
build constants are not module API — they are build identity, like the
`standard.*` prelude — so they are ambient and need no `imports` row. Only
`constant` is exempt; everything else, stdlib included, is imported explicitly. A
`configure` operation's `BuildPlan` (§30.3.2) may compute constants dynamically;
static `PROJECT constant` rows and `BuildPlan`-produced constants share one
namespace, and a collision between them is a hard error.

### 28.2 Source layout and the `.sem` family

```
myproject/
  build.sem            # manifest: identity + deps + build config
  build.sem.lock       # generated, committed
  src/
    main.sem           # entry module's root file
    main.test.sem      # co-located tests (Go _test.go style)
    routes/
      main.sem         # a submodule is a directory; main.sem is its root file
    internal/
      auth/main.sem    # importable only within this module tree (enforced)
  assets/  sql/        # non-source resources
  dist/                # build OUTPUT, gitignored
```

`.sem` is the sole source extension. The coherent family:

| Extension | Role |
|---|---|
| `.sem` | source and SemanticScript-data config (`build.sem`, module source) |
| `.sem.lock` | generated lockfile (read-only artifact) |
| `.test.sem` | tests |
| `.semsig` | distributed signature sidecar (§26) |

`.sscript` is a deprecated alias accepted with a warning; new files use `.sem`.

Layout rules:

- Everything compiled lives under `src/`; manifest, lock, assets, and output
  stay outside it.
- `main.sem` is the conventional **root file of any module directory** — "main"
  means the directory's primary file, not necessarily an entrypoint (matches
  `std/<module>/main.sem` and existing app submodules).
- The program entry is declared in `build.sem` (`entry`), not by filename.
- `src/internal/...` is importable only by code rooted at `internal/`'s parent
  (Go's rule), resolver-enforced. Combined with entity-level `exports` (§7) this
  gives two visibility layers: `exports` controls visibility within a module, and
  `internal/` controls it across modules.
- Build output goes to `dist/` (gitignored), never `build/` — a `build/` output
  directory would collide with the `build.sem` manifest.

### 28.3 Module identity and import paths

A module's identity is its **import path, which is its repository path**:
`github.com/user/repo/sub/module`. The stdlib keeps the one privileged short
namespace, `standard.*`, bundled with and version-locked to the toolchain.

**Module discovery.** `PROJECT module <name>` in `build.sem` names only the
**root** module. Every other module is discovered by directory layout (§28.2):
each directory under `src/` containing a `main.sem` is a module, and its import
path is the repository path plus the directory's path relative to `src/`
(`src/routes/` → `<repo>/routes`). There is no per-submodule manifest row —
adding a directory with a `main.sem` registers a module; `src/internal/...`
restricts that module's import visibility to code rooted at `internal/`'s parent
(§28.2).

Because versions live only in `build.sem` (§28.1), `imports` rows are stable
across upgrades and a bump produces a one-line manifest diff, not a source-wide
churn.

### 28.4 Versioning, resolution, and the module cache

- **Semver git tags** (`v1.4.0`) are the version source; no registry.
- **Minimal Version Selection** picks, for each module, the highest version
  named in any reachable `require` row — deterministic without a solver.
- **Content-addressed integrity**: every selected version is pinned by sha256 in
  `build.sem.lock`. A digest mismatch is a hard error.
- **Global module cache** (Go's `pkg/mod` analog), shared across projects,
  populated from the lock. No `node_modules`, no vendoring by default.
- **`sem vendor`** is opt-in, for hermetic or offline builds; it copies the
  resolved tree into `vendor/` and the build prefers it.
- **`replace`** redirects a dependency to a local path for multi-repo dev.

Commands (proposals, per §24's spec-status note — the current CLI exposes
`sem deps ...` for dependency inspection and does **not** yet implement
`sem get`/`sem mod`/`sem vendor` or `sem test --lane`):

```bash
sem get github.com/foo/markdown@v2.1.0   # add/upgrade a dependency        (proposed)
sem mod tidy                             # resolve, write build.sem.lock    (proposed)
sem vendor                               # materialize vendor/ for hermetic builds (proposed)
```

### 28.5 Capability-scoped dependencies

A dependency declares its full effect surface through ordinary `effect`/`grants`
data (§8). The resolver aggregates that surface across the dep tree into
`build.sem.lock` and checks it against an allowlist in `build.sem`:

```sem
TaskApp allowEffect read   fs.cwd
TaskApp allowEffect write  console.stdout
TaskApp allowEffect readWrite database
```

```
$ sem get github.com/foo/markdown@v2.1.0
  markdown v2.1.0 requests capabilities:
    write  console.stdout      ✓ allowed
    read   net.socket          ✗ NOT in allowlist
  refusing to add: a markdown formatter should not open sockets.
  override with:  TaskApp allowEffect read net.socket
```

A pure formatter that later starts opening sockets fails the build, because its
declared effects no longer fit the allowlist — a compile/link-time supply-chain
guarantee, not a runtime sandbox.

**Open decision (proposed default: fail-closed).** This spec proposes the
allowlist is **hard-fail by default** — an uncovered effect blocks the build,
matching the language's broader "no hidden failures / authority is source data"
stance — with explicit per-effect opt-in. A warn-by-default mode would be the
alternative; that choice shapes the lock's capability section and must be
settled before implementation.

### 28.6 Distribution via `.semsig`

A published library distributes its signatures as `.semsig` files (§26), one per
module path, content-addressed and referenced from `build.sem.lock`. This lets
the toolchain **typecheck and lint a consumer against a dependency without its
source** (fast CI; pre-vetting a package's contract and effect surface before
fetching its body) and is the agent-facing contract surface: an agent reasons
about a dependency from its compact `.semsig`, not its implementation.

### 28.7 Testing structure

| Lane | Lives in | Form |
|---|---|---|
| unit / semantic | co-located `*.test.sem` | SemanticScript |
| component / integration / e2e | `tests/` | SemanticScript, multi-module |
| golden / snapshot | `tests/golden/` | content-addressed expected output |

- Tests are SemanticScript via a `standard.test` module plus a native
  `sem test --lane <lane>` runner (the `--lane` flag is **proposed**; the current
  CLI runs `sem test` without lanes) — not external Python harnesses. This keeps
  the test contract inside the language and aligns with the minimal-runtime /
  logic-in-stdlib principle. The concrete test-operation shape (the `tag test`
  row, `out TestResult`, `assert.*` targets) is specified in §30.5.1.
- Golden tests pin expected codegen or formatter output by sha256, reusing the
  digest primitive.
- Existing Python harnesses migrate to `.test.sem` opportunistically; Python is
  kept only where a genuine external black-box driver is required.

### 28.8 Conversion from the current app layout

| Current | Framework layout |
|---|---|
| `apps/x/build.sem` (build plan only) | `x/build.sem` (build plan + `require`/`replace`/`allowEffect`) |
| *(no lockfile)* | `x/build.sem.lock` (generated by `sem mod tidy`) |
| `apps/x/main.sem` at app root | `x/src/main.sem` |
| `apps/x/components/main.sem` | `x/src/components/main.sem` |
| output in `apps/x/build/` | output in `x/dist/` (gitignored) |
| `apps/x/scripts/test_*.py` | `x/tests/*.test.sem` (+ `standard.test`) |
| `modulePath: "github.com/.../apps/x"` | unchanged — already the import path |

Migration is mechanical: move source under `src/`, rename the output directory,
add manifest dependency/allowlist rows, and run `sem mod tidy`.

---

## 29. Open gaps and specification roadmap

This section is **informative** — a planning surface, not normative spec. It
tracks what v0.3 already specifies versus what remains before EAV can become the
mandatory authoring surface (see "Adoption framing" and §21). The point is to
distinguish *genuinely unspecified* work from *present-but-informal* rules that
only need formalization, so effort is not spent re-deriving what already exists.

**Status legend:**
- **Absent** — not specified yet; green-field work.
- **Thin** — rules/intent present but informal; needs formalization or
  edge-case closure, not invention.
- **Partial** — substantially specified; needs finishing.

Three gaps (#3, #6, #7) are also obligations of the project **change protocol**,
which requires parser, linter, docs, tests, and editor support to move together.
They are contract requirements, not optional polish.

### 29.1 Gap register

| # | Gap | Status | Wave | Primary refs |
|---|---|---|---|---|
| 3 | **Lowering plan** — EAV → existing `semsc.py` AST / compiler / backend; shared-AST claim made never specified | Absent | 1 | Adoption framing |
| 11 | **`sem fmt` determinism** — total + idempotent + order-stable (`fmt(fmt(x)) == fmt(x)`) | Absent | 1 | §22 |
| 6 | **Conformance test matrix** — parser/formatter/linter/lowering/editor goldens | Absent | 2 | §17, §18, §19 |
| 12 | **Diagnostic-code registry** — code → meaning → tier → repair, one canonical table | Absent | 2 | §17, §24 |
| 1 | **Formal grammar** — EBNF, token classes, island parse rules, invalid-example corpus | Thin | 3 | §2, §5, §16 |
| 2 | **Executable semantics** — consolidate + close edges (defer×goto, error-path liveness, eval order, error chaining) | Thin | 3 | §12, §13, §15.6, §25 |
| 7 | **Editor/LSP plan** — tokens, hovers, completions, rename, code actions, symbols, diagnostics | Absent | 4 | — |
| 5 | **Tooling contract** — CLI args, JSON schemas, exit codes, MCP equivalents | Thin | 4 | §24, §17 |
| 10 | **Security/trust enforcement** — URL-hole proof, call-graph capability coverage, trust-boundary runtime | Thin | 5 | §8, §16, §26, §28.5 |
| 9 | **Stdlib/.semsig** — formal field schema, versioning, docs-generation path | Partial | 5 | §26, §28.4, §28.6 |
| 4 | **Migration guarantees** — round-trip, codemod *correctness* criteria, unsupported-edge list | Partial | 6 | §20, §23 |
| 8 | **Versioning & rollout** — feature flags, compatibility mode, milestones, deprecation policy | Partial | 6 | §21, Adoption framing |
| 13 | **Spec coherence** — normative/informative labeling, single source of truth, glossary | Absent | all | (cross-cutting) |
| 14 | **Runtime value semantics** — numeric overflow/trap, IEEE float, equality/ordering, eval order, value lifetime/memory model | Thin (source contract §10.6; backend mechanism open) | 3 | §10.6, §13 |
| 15 | **Agent edit loop + diagnostic source-mapping** — check→fix→patch→verify on EAV; lints on canonical EAV mapped back to the author's compact/current line | Absent | 4 | §17, §23, §24 |
| 16 | **Human-authoring validation** — learnability of the reserved-word/predicate surface, reviewability of large handlers, compact-profile ergonomics | Absent | 6 | §0, §23 |
| 17 | **Existing-corpus migration** — whether stdlib + apps convert to EAV, codemod correctness, permanent coexistence | Thin | 6 | §20, §28 |
| 18 | **Runtime observability & debugging** — logging/metrics/spans/correlation IDs; breakpoints, stepping, stack traces under goto control flow, trap/panic formatting, and mapping a runtime failure back to its EAV/current source span; how `sem trace` relates to live debugging | Absent | 5 | §24, §30.1.1 |
| 19 | **Security threat model** — assets/adversaries (authority, trust, supply chain), distinct from the #10 enforcement algorithm | Thin | 5 | §8, §16, §28.5 |
| 20 | **Strategic success criteria** — win condition vs. hardening current syntax and vs. competitors; multi-surface maintenance cost | Absent | all | §21, Adoption framing |
| 21 | **Performance & profiling** — resource budgets beyond `memory`, allocation/hot-path reporting, optimization controls, perf diagnostics | Absent | 5 | §10.6, §11 |
| 22 | **Text & i18n** — Unicode normalization, grapheme model, locale-aware comparison/casing/collation, formatting, translation (today: bytewise UTF-8 only) | Absent | 6 | §10.6, §30.2.2 |
| 23 | **Publishing & distribution workflow** — publish/auth, private deps, provenance, vulnerability advisories, yank/retraction, discovery (beyond MVS resolve) | Thin | 6 | §28.4, §28.6 |
| 24 | **Macros / metaprogramming / reflection** — codegen-in-language, compile-time reflection, schema introspection (const-fold §30.3.2 is the only adjacent piece) | Absent | 6 | §30.3.2 |
| 25 | **Deployment & runtime configuration** — runtime config, secrets, env profiles, schema migrations, operational config (distinct from build config, §28) | Absent | 6 | §28, §30.5.3 |
| 26 | **Resource ownership edge semantics** — ownership transfer, aliasing an owned handle, double-cleanup, escape-via-`return` | Absent | 3 | §15, §15.6, §32.1 |
| 27 | **Semantic diff** — row-aware typed deltas (effect added, cleanup removed, route/arity changed) for review + supply-chain | Absent | 4 | §28.5, §32.3 |

### 29.2 Sharpened scope per gap

**#14–#25 (added in later revisions).** #14 *runtime value semantics*: §10.6 now pins
the **source contract** (two's-complement wrap, div-by-zero trap, IEEE-754,
bytewise-UTF-8 `String` equality, enum-by-variant, arg eval order, no-free value
lifetime); the open part is the backend *mechanism* (region / arena / refcount).
#15 *agent loop + diagnostic mapping*: the "agent-safe IR" payoff needs the
check→fix→patch→verify loop specified against the `sem.*.v1` surfaces, plus a
rule that a diagnostic computed on canonical EAV maps back to the author's
compact/current source span. #16 *human-authoring validation* and #20 *success
criteria* are evidence gaps — run a real human-authoring session and define the
win condition (vs. hardening current syntax; vs. the competitor framing) before
EAV is made mandatory (§21). #17 *existing-corpus migration*: decide whether the
stdlib and apps convert, prove the codemod, or commit to permanent coexistence.
#18 *runtime observability* and #19 *security threat model* (§8) round out the
operational and security surfaces. #21 performance, #22 text/i18n, #23 publishing,
#24 macros/reflection, and #25 deployment/config are the operational and ecosystem
subsystems §32 decomposes — mostly stdlib/runtime work beyond the core language.

**#3 Lowering plan (keystone).** The Adoption framing claims both surfaces "map
to the same canonical EAV form," implying a shared AST with current syntax — but
nothing states whether EAV parses into the same `semsc.py` AST, which compiler
structures change, or whether EAV is a pre-parser normalization vs. a second
front-end. Until pinned, tooling, tests, and editor work have no anchor.

**#11 `sem fmt` determinism.** The whole "tools operate on canonical EAV" thesis
rests on `fmt` being total, idempotent, and order-stable under §22 ordering.
State it as a guaranteed invariant and test it; it underlies #4 and #6.

**#6 Conformance test matrix.** §18/§19 are golden *candidates* and §17
invariants are fixture *candidates*, but no matrix ties them together. Must honor
the project rule that no behavior is "implemented" without a test that would fail
under a no-op lowering.

**#12 Diagnostic-code registry.** Codes are scattered (SS1305/1502/1610, MD10xx
in §17; SS3104 elsewhere). `sem explain SSxxxx` already promises a registry;
make it one canonical table. Feeds #5 and #6.

**#1 Formal grammar.** §2 (lexical rules, punctuation, reserved words) and §5
(per-kind predicates) already supply token classes and the predicate grammar
informally — formalize into EBNF + invalid examples. **Parse precedence is
mostly N/A by design** (no expressions/infix). The real sub-gap is **island
parsing** (§2 indentation-is-semantic + §16): precise enter/exit/dedent rules.

**#2 Executable semantics.** More exists than it appears (defers §13, async
lifecycle table §13, nil/Result arity §13, cleanup §15.6, path-sensitive
liveness §25, rebinding/globals §12) but is scattered. Value construction and
access (§10.5), user-operation invocation (§15), payloadless-enum discrimination
(§13), operation bodies (§11), entry/context ABIs (§11), and sync-fallback async
semantics (§13), and data-carrying enum/error **destructuring** via the
`ifVariant` guard (§13, §10.5) are now specified. Consolidate the rest, then close:
(a) defer × goto-that-does-not-return; (b) liveness on partially-initialized
error paths; (c) intra-row evaluation order; (d) **error chaining, which §13
explicitly punts** — required before `onFailure propagate` can ship.

**#7 Editor/LSP plan.** Change-protocol step requires the vscode extension
(grammar, semantic tokens, hover, symbol index) to move with the parser. The
subject-anchored row model (col 1 = subject, col 2 = predicate) is a
tokenization *advantage* worth specifying explicitly.

**#5 Tooling contract.** §24 self-declares "proposals." Bind them to the
*existing* `sem.*.v1` JSON surfaces and MCP tool mappings rather than inventing
new schemas; diagnostic codes already partially exist (§17).

**#10 Security/trust enforcement.** Rules exist as intent + hard-error invariants
(§16 HTML holes, §8 effect coverage, §17 #33/#34, §26 `trustConstraint`); the
*algorithm* does not (how a URL-bearing hole is proven, how capability coverage
is computed across the call graph). Must reconcile with §28.5's compile-time
supply-chain capability model — same authority model, two locations.

**#9 Stdlib/.semsig.** §26 covers format, resolution order, and first-match
conflict behavior. Missing: a formal field schema, `.semsig` versioning, and a
docs-generation path. **Specify `.semsig` versioning once**, unified with the
packaging story (§28.4/§28.6), to avoid divergence.

**#4 Migration guarantees.** §20 (14-step procedure) and §23 (compact↔EAV) cover
the mapping. Missing: round-trip guarantees (is current→EAV→current lossy, and
where?), codemod acceptance criteria about *semantic equivalence* (the §21 gate
measures rows/locality, not correctness), and an enumerated unsupported-edge
list.

**#8 Versioning & rollout.** §21 + Adoption framing already define the *adoption
gate* (the "when does EAV become mandatory" answer). Distinct and missing: the
*engineering rollout* — feature flags, compatibility-mode definition,
milestones, deprecation timeline.

**#13 Spec coherence (cross-cutting).** With overlapping topics across sections
(.semsig in §26 vs §28; capability enforcement in §8/§17 vs §28.5; tooling in
§24 vs existing `sem.*.v1`), add normative/informative labels, a single source
of truth per topic, and a glossary, or sub-specs will drift.

### 29.3 Execution order

The Wave column groups the work so each wave unblocks the next:

1. **Wave 1 — anchor:** #3 lowering, then #11 fmt determinism (its corollary).
2. **Wave 2 — lock behavior:** #6 test matrix, #12 code registry.
3. **Wave 3 — formalize:** #1 grammar, #2 semantics consolidation.
4. **Wave 4 — contract surfaces:** #7 editor/LSP, #5 tooling — against existing
   `sem.*.v1` and MCP.
5. **Wave 5 — authority:** #10 security enforcement, #9 `.semsig` — unified with
   §28's models, not duplicated.
6. **Wave 6 — finish migration:** #4 round-trip guarantees, #8 rollout mechanics.
7. **Threaded throughout — #13 coherence.**

**Later gaps (#14–#27)** attach to the waves above rather than forming new ones:
#14 memory mechanism and #15 diagnostic source-mapping ride on Wave 1 (#3
lowering); #18 observability, #19 threat model, and #23 publishing fall in Wave 5
(authority/ecosystem); #16 human-authoring, #17 corpus migration, and #20 success
criteria are evidence gates beside Wave 6 and the §21 adoption gate; #21
performance, #22 i18n, #24 macros/reflection, and #25 deployment/config are
post-v0.3 stdlib/runtime work; #26 ownership edges sit in Wave 3 (semantics) and
#27 semantic diff in Wave 4 (tooling). So every §29.1 register row has a wave, as §29.4
states.

### 29.4 Subsystem coverage map

Where each language-subsystem question is dispositioned, so "is X covered?" has
one answer:

| Subsystem | Disposition |
|---|---|
| Pattern matching / data inspection | **Specified** — `ifVariant` guard (§13) + construction/access (§10.5) |
| Value semantics (numeric, equality, lifetime) | **Specified (source contract)** — §10.6; backend mechanism is roadmap #14 |
| String assembly | **Specified** — §30.2.2 (stdlib `string.*`); i18n is roadmap #22 |
| Collections (list/array/map) | **Deferred** — §27 (interim: opaque stdlib handles + goto loop) |
| Generics / type parameters | **Deferred** — §27 (interim: monomorphize) |
| Structured loops | **Deferred** — §27 (interim: labeled gotos) |
| Concurrency primitives | **Deferred** — §27 (interim: cooperative `task`) |
| Retry / timeout / cancel policy | **Deferred** — §27 (interim: goto/timer) |
| FFI / native ABI + opaque types | **Mechanism fixed, mapping deferred** — §30.4, §27 |
| Full stdlib API catalogs | **External surface** — §27 (`.semsig` + docs, §26) |
| System APIs (fs/process/env/clock/random/net) | **External surface** — §27 (capability-gated `standard.*`) |
| GUI / browser DOM | **External surface / future target** — §27, §7 |
| JSON / serialization / codecs | **External surface** — §27, §16 (`standard.json`, roadmap) |
| Testing | **Specified** — `tag test` + `standard.test` (§30.5.1, §28.7) |
| Determinism / replay | **Specified** — `mode capturedOutputReplay` (§30.1.1) |
| Doc generation | **Specified** — `sem docs` from metadata (§30.6.1) |
| Diagnostic suppression | **Specified** — `suppress … because` (§30.6.2) |
| Build / dependency model | **Specified** — §28 (build.sem/lock, MVS) |
| Security: authority / trust / supply-chain | **Threat model §8**; enforcement algorithm is roadmap #10/#19 |
| Memory mechanism | **Roadmap #14** (source contract is §10.6) |
| Runtime debugging & observability | **Roadmap #18** |
| Performance & profiling | **Roadmap #21** |
| Text & i18n | **Roadmap #22** |
| Publishing / distribution workflow | **Roadmap #23** (resolve/MVS is §28) |
| Macros / metaprogramming / reflection | **Roadmap #24** |
| Deployment / runtime config | **Roadmap #25** |
| Resource ownership edges | **Roadmap #26** — source rows exist (§15/§15.6); transfer/alias/double-cleanup/escape rules open |
| Semantic diff | **Roadmap #27** — row-aware typed deltas (§32.3) |

*Specified* = usable in v0.3; *Deferred* = needs future syntax, with an interim
pattern in §27; *External surface* = stdlib/ecosystem, out of the core by design;
*Roadmap* = tracked in §29.1 with a wave.

---

## 30. Edge features and resolutions

This section resolves syntax-adjacent features that were implied by the grammar
but unspecified, or peripheral to it. Each subsection is **Normative** (a v0.3
decision) or **Roadmap** (mechanism fixed, detail deferred). §30.7 collects the
tokens introduced so §2's reserved set and §13's guard set stay the single
source of truth.

**Coherence boundary.** Value semantics are owned elsewhere and are *not*
re-specified here: numeric overflow/trap, equality/ordering, evaluation order,
and value lifetime are §10.6; record/enum/error construction and access, and
data-carrying *destructuring* via the `ifVariant` guard, are §10.5/§13 (see §27
and §29 #2). §30 covers only the edges those sections do not own, and adds no new
control-flow guard — variant dispatch is owned by §13's `ifVariant`.

Design constraints honored throughout: no expressions, no block delimiters, flat
one-row-one-record tape, control flow via labeled gotos, and capabilities as the
authority/effect seam.

### 30.1 Features already in the grammar — now specified

#### 30.1.1 `mode capturedOutputReplay` — Normative

A `PROJECT mode capturedOutputReplay` row — a predicate on the `project` entity
in `build.sem` (§5, §7), not a bare top-level row — puts the runtime in capture/replay
determinism mode. Every capability-mediated external effect (console writes,
clock reads, random draws, env reads, network/db results) is routed through a
**transcript**: on a *record* run the runtime appends each effect's inputs and
observed result; on a *replay* run it feeds the recorded result instead of
performing the effect.

- The transcript is ordered by effect-execution order and keyed by capability +
  call site, so it is stable as long as control flow is.
- It is the substrate for golden tests (§29 #6), `sem trace` (§24), and runtime
  observability (§29 #18): a replay run is deterministic and side-effect-free.
- Only capability-mediated effects are captured, so a program that takes time
  and randomness through capabilities (§30.5.3) is fully replayable.
- The transcript wire format is content-addressed; its exact schema is part of
  the test-matrix work (§29 #6) and is not frozen in v0.3.

A program with no `mode` row runs in ordinary direct-effect mode.

#### 30.1.2 Duration literals — Normative

Duration literals are the `<number><unit>` form that the retry, interval, and
timeout rows consume. Those consuming rows are all deferred to a future version
(§27), so v0.3 contains no duration literal in practice — the literal class and
the `Duration` alias are fixed now so the lexer and type stay stable when those
rows land. §2's literal grammar did not previously cover this form. A duration
literal is `<integer><unit>` with no
intervening space (same no-space rule as negative literals, §2):

```
unit ∈ { ns, us, ms, s, m, h }
```

`us` is microseconds. Duration literals are valid only in duration-typed
positions and lower to the stdlib `Duration` alias (`Int64` nanoseconds; the
time aliases are stdlib-defined, §27). There is no float duration literal —
compose sub-unit precision with a smaller unit (`1500ms`, not `1.5s`). Examples:
`50ms`, `500ms`, `30s`.

### 30.2 Initialization and string assembly

#### 30.2.1 Module initialization order — Normative

Module initialization in v0.3 is **exactly** module-level `storage` initializer
evaluation (§12) — there is no separate init row or init operation. It runs
**before** `entry`, in this order:

1. Imported modules initialize before importing modules (dependency order).
2. Within a module, `storage` entities initialize in document order.

Module-`storage` initializers must be **effect-free** — a literal, a build
`constant`, or a reference to already-initialized module storage (§12) — since
`storage` has no `effect`/`uses` predicates. Effectful setup (opening a shared
resource, reading the environment) belongs in the entry operation or, for a
`webServer`, the `startup` handler (§14), not in module init. A cyclic
initialization dependency between modules is a hard error. A
failing initializer traps (§10.6) — there is no caller to receive a `Result` at
init time. For a `webServer` target, module-`storage` initialization completes
before the `startup` handler (§14) runs; `startup` is application-level setup
that may assume module storage is already initialized.

#### 30.2.2 String assembly — Normative

There is no string interpolation and no concatenation operator (no expressions).
Strings are assembled exactly one way: by stdlib calls — `string.concat` /
`string.join` for fixed structure, `string.format` with a format string plus
positional typed args (the width/format discipline the linter already checks).
Structured document text (HTML) uses the template island (§16), not string
building. (String *equality* is §10.6; this row is only about construction.)
This is the single, explicit answer to "how do I build a string."

### 30.3 Targets and compile-time

#### 30.3.1 Target-gated entities — Normative

Code that varies per target (console vs `wasm` vs `webServer`) is **not** a
preprocessor — that would break the flat, greppable model. Gating is a
declaration predicate on the entity:

```
<entity> forTarget <target>
```

An entity with no `forTarget` row is included for all targets. An entity with one
or more `forTarget` rows is included only when the built target matches. The
predicate is data, so every variant is visible and greppable in one file; there
are no hidden `#if` branches. Lint: the `entry` entity must resolve for the
target being built.

**Reference closure (pruning).** Gating prunes an entity from a build; the
reference graph must stay closed for each built target. If an entity *included*
for the built target references a *pruned* one — `do`/`start`/`defer`/`uses`/
`cleanedBy`/`invokes`/`exports` it — that is a hard error (dangling reference for
that target), not a silent drop. Provide a same-target alternative (its own
`forTarget`) at every reference site.

**Filtering phase.** Gating is resolved **first**, before lint/check/codegen: the
toolchain selects the entity set for the built target+platform, then every later
phase (lint, type/effect check, lowering) operates **only** on that filtered set.
A pruned entity is never linted or compiled for a build it is excluded from, and
the reference-closure check runs against the filtered set — a reference to a
pruned entity surfaces as a hard error in the check phase, not a silently dropped
row.

**Platform gating.** `<entity> forPlatform <name>` is the platform-level sibling
of `forTarget`, gating an entity to a declared `platform` entity (§28.1). The
same inclusion and reference-closure rules apply per built platform; `<name>`
must be a declared platform or it is a hard error. `forTarget` and `forPlatform`
may both appear on one entity (logical AND).

#### 30.3.2 Compile-time evaluation and asset embedding — Normative

Build-time execution is a project's **`configure` operation**, named by a
`PROJECT configure <operationName>` row in `build.sem` (§28) and declared in the
project's **root module** (the one named by `PROJECT module`) — `project` has no
`imports` predicate, so there is no separate build-module import. It has
`out BuildPlan` (a `standard.build`
record naming targets, output paths, and constants), runs once before any target
is compiled, may read build inputs only through build-time capabilities (no
runtime effects), and its result configures the build. Generalized rule for v0.3:
an operation with no effects and only constant inputs **may** be evaluated at
compile time and its result folded as a constant. Asset embedding uses `literalSource` to inline a
file's bytes at compile time, content-addressed by `literalDigest` (§27 maps the
legacy `domainLiteral*`/`literalBytes` rows here). Effectful or input-dependent
operations are never const-folded.

**`BuildPlan` / `BuildTarget` shape.** `BuildTarget` is a `standard.build` record
with fields `name String`, `target String` (the `console`/`webServer`/`wasm`
model), `platform String` (a declared `platform` name), and `output String`
(path). `BuildPlan` is an opaque `standard.build` value assembled by calls rather
than a literal (no in-language collections, §27). Constructor `.semsig`
signatures:

```sem
buildEmptyPlan is intrinsic
buildEmptyPlan target build.emptyPlan
buildEmptyPlan out BuildPlan

buildTarget is intrinsic
buildTarget target build.target
buildTarget arg name String
buildTarget arg target String
buildTarget arg platform String
buildTarget arg output String
buildTarget out BuildTarget

buildWithTarget is intrinsic
buildWithTarget target build.withTarget
buildWithTarget arg plan BuildPlan
buildWithTarget arg entry BuildTarget
buildWithTarget out BuildPlan

buildWithConstant is intrinsic
buildWithConstant target build.withConstant
buildWithConstant arg plan BuildPlan
buildWithConstant arg name String
buildWithConstant arg value String
buildWithConstant out BuildPlan
```

`configure` threads a `let mutable BuildPlan` from `build.emptyPlan` through
`build.withTarget`/`build.withConstant` and returns it. **Merge/validation:**
`build.withTarget` with a `BuildTarget` whose `name` already exists replaces it;
every `BuildTarget` must name a declared `platform` and a static `PROJECT target`
(§28.1 precedence), or it is a hard error.

**`configure` lifecycle.** The `configure` operation runs only at build time and
is **excluded from every runtime build** (never compiled into a target binary).
It is referenced by the `PROJECT configure` manifest row, not imported, so it need
**not** be exported. It runs **once for the whole build**, before per-target
compilation, and is therefore **not** target- or platform-gated (`forTarget`/
`forPlatform` on a `configure` operation is an error).

**Build-time capabilities.** A `configure` operation may `uses` only build-time
capabilities — read-only access to build inputs over the `build.*` resource
namespace (`build.fs.read`, `build.env`, `build.gitTag`, …) — never the runtime
resources of §8 (`console.stdout`, `database`, `http.response`, …). A runtime
effect on a `configure` operation is a hard error, keeping the build graph
effect-light and replayable. Build-time capabilities are ordinary `capability`
entities (§8) whose `grants` name `build.*` resources; the toolchain provides the
`build.*` namespace, so — like `console`/`compare` — it needs no import. They are
declared in the `configure` operation's module and named by its `uses` rows,
exactly like runtime capabilities; only the resource namespace differs. The root
module imports `standard.build` for the `BuildPlan` type
(`imports build standard.build`); there is no implicit import.

**Precedence.** Static manifest rows define project identity and are
authoritative: a `BuildPlan` may compute output paths, per-platform overrides,
and constants, but may not contradict a static `PROJECT target`/`require`/
`platform`/native-link row — such a conflict is a hard error. Configure *refines*
(output, constants, overrides); it never *overrides* identity. (Static
`PROJECT constant` vs `BuildPlan`-produced constant collisions are a hard error,
§28.1.)

### 30.4 Interop and extensibility — Roadmap (mechanism fixed)

#### 30.4.1 Foreign function interface

Binding a non-stdlib C library reuses the existing extern mechanism rather than
adding new syntax: declare an `is intrinsic` signature (§26) per foreign
function, ship it in a `.semsig`, and declare the native link inputs (library,
header, link flags) as rows in `build.sem` alongside `require`. Typed wrappers,
capabilities, and trust boundaries are ordinary `.sem` over those intrinsics —
the same shape the stdlib uses. The native-link inputs are `project` rows in
`build.sem`:

```
PROJECT nativeLibrary <name>      # link a native library, e.g. nativeLibrary sqlite3
PROJECT nativeHeader "<path>"     # header included for signature checking
PROJECT nativeLinkFlag "<flag>"   # raw linker flag, e.g. "-L/usr/local/lib"
```

The full FFI type-mapping (`OpaquePointer`, `FileHandle`, struct/by-value ABI) is
deferred (§27), but the mechanism is fixed: **intrinsic + `.semsig` +
`build.sem` native-link rows, no new core syntax.**

#### 30.4.2 C-callable exports

The reverse direction — exposing a `.sem` operation as a C symbol so other
languages embed SemanticScript — is roadmap. Shape: an `OP export c <symbol>`
declaration row on an operation whose `in`/`out` types are all C-ABI-representable.
`export` is an operation predicate (§5) and the row sorts after the operation's
metadata, before its first step (§22). `c` is the only ABI tag in v0.3; `<symbol>`
is a C identifier (`[A-Za-z_][A-Za-z0-9_]*`). At most one `export c` row per
operation, and each `<symbol>` must be unique across the build (collision is a
hard error). An `export c` operation may still be `forTarget`/`forPlatform`-gated.
The toolchain emits the symbol plus a generated header. Deferred until the FFI
type-mapping (§30.4.1) is specified.

### 30.5 Testing and determinism

#### 30.5.1 Test operations — Normative

A `.test.sem` file declares ordinary operations marked for the test runner with
the universal `tag test` metadata row (§6) — no new core syntax. A `.test.sem`
file is **part of the same module** as the source it sits beside (§28.2), so it
invokes that module's operations by bare name (`addTwoValues` below resolves to
the module's operation, §15). Two stdlib modules split the surface:
`standard.assert` provides the assertion targets (imported as `assert` →
`assert.equalInt64`/`assert.true`/`assert.matchesGolden`), and `standard.test`
provides the `TestResult` type and result combinators (imported as `test` →
`test.and`). A test operation takes no inputs and returns `out TestResult`; its
assertion calls fail the test on mismatch:

```sem
taskTests imports assert standard.assert
taskTests imports test standard.test

addsTwoNumbers is operation
addsTwoNumbers tag test
addsTwoNumbers out TestResult
addsTwoNumbers purpose "addTwoValues returns the sum of its inputs"
addsTwoNumbers let leftInput immutable Int64 40
addsTwoNumbers let rightInput immutable Int64 2
addsTwoNumbers let expectedSum immutable Int64 42
addsTwoNumbers do computeSum
addsTwoNumbers do checkSum
addsTwoNumbers return testOutcome

computeSum is call
computeSum in addsTwoNumbers
computeSum invokes addTwoValues
computeSum arg leftValue Int64 leftInput
computeSum arg rightValue Int64 rightInput
computeSum out sumValue Int64

checkSum is call
checkSum in addsTwoNumbers
checkSum invokes assert.equalInt64
checkSum arg expected Int64 expectedSum
checkSum arg actual Int64 sumValue
checkSum out testOutcome TestResult
```

**Concrete API.** `TestResult` is a `standard.test` record (a pass/fail flag, a
message, and an assertion count). The `.semsig` signatures (§26):

```sem
assertEqualInt64 is intrinsic
assertEqualInt64 target assert.equalInt64
assertEqualInt64 arg expected Int64
assertEqualInt64 arg actual Int64
assertEqualInt64 arg message String              # failure message
assertEqualInt64 out TestResult

assertTrue is intrinsic
assertTrue target assert.true
assertTrue arg actual Bool
assertTrue arg message String
assertTrue out TestResult

assertMatchesGolden is intrinsic
assertMatchesGolden target assert.matchesGolden
assertMatchesGolden arg actual String            # produced output to compare
assertMatchesGolden arg goldenPath String         # path under tests/golden/
assertMatchesGolden arg expectedDigest String     # sha256 of the committed golden
assertMatchesGolden out TestResult

testAnd is intrinsic
testAnd target test.and
testAnd arg left TestResult
testAnd arg right TestResult
testAnd out TestResult
```

**Golden tests.** `assert.matchesGolden` compares `actual` against the committed
golden at `goldenPath` and verifies its `sha256` equals `expectedDigest`; a
mismatch fails the test. Regenerating a golden is an explicit, opt-in toolchain
action (`sem test --update-golden`, proposed) that rewrites the file and re-pins
the digest — goldens are never updated implicitly on a normal run.

**Combining results without arrays.** v0.3 has no variadic or array, so there is
no `all(list)`: combination is the **binary** `test.and left right` (fails if
either fails), folded through a `let outcome mutable TestResult` across many
assertions (or a labeled-goto loop over `let` fixtures, §13). A single-assertion
test returns its assert's `out` directly.

**Lanes.** `tag test` marks the operation a test; an optional second tag selects
its lane (`tag unit` | `tag integration` | `tag e2e`), defaulting to `unit`. The
`sem test --lane <lane>` runner (proposed; §28.7) discovers `tag test` operations
and groups them by that lane.

**Failure semantics.** An assertion mismatch produces a **failing `TestResult`**
— it does not trap; the operation returns it and the runner records the failure
and its message. A test that *traps* (e.g. a div-by-zero, §10.6) is reported as a
distinct runtime error, not a failed assertion. Table-driven cases are `let`
fixtures iterated by a labeled-goto loop (§13). Golden cases assert against a
content-addressed expected output (`assert.matchesGolden`), tying into the test
matrix (§29 #6) and `mode capturedOutputReplay` (§30.1.1).

#### 30.5.2 Capability injection as the test-double seam — Normative

Because an operation binds to a capability **entity** (`uses`, §8), a test
supplies a substitute capability whose `grants` match the real one but whose
backing is a fake. This is the test-double mechanism: no mocking framework, no
dependency-injection container — the capability is the seam. A test wires the
operation's capability environment to fakes (an in-memory `dbReader`, a
fixed-result `httpClient`) and exercises the operation unchanged.

#### 30.5.3 Nondeterministic inputs as capabilities — Normative

`clock`, `random`, and `environment` are reached only through capabilities /
opaque inputs, never ambient globals. Injecting a fixed-clock or seeded-random
capability makes a run deterministic, and combined with `mode
capturedOutputReplay` (§30.1.1) makes it fully replayable. This is why time and
randomness are modeled as authority, not built-ins.

**Time-safety typing (X-095).** `standard.clock` exposes two distinct 64-bit
(Y2038-safe) instant types: `WallTime` (UTC/display) and `MonotonicInstant`
(durations/timeouts). Applying arithmetic (`math.*`) to a `WallTime` operand is a
hard error (**SS3095**) — wall-clock time has no arithmetic: measuring elapsed
time subtracts two `MonotonicInstant`s (`clock.elapsedMillis`), and calendar math
requires an explicit timezone conversion. This makes "measured elapsed time with
the wall clock" and "naive local-time arithmetic" unrepresentable rather than
silently wrong.

### 30.6 Documentation and suppression

#### 30.6.1 Doc generation from source — Normative

The documentation source is already in the language: universal metadata
(`purpose`/`invariant`/`note`/`rationale`/`risk`/`example`, §6) plus the typed
comment vocabulary (`# rationale:`, `# warning:`, `# security:`, …). `sem docs`
generates module and operation documentation from these, and the same metadata
feeds `.semsig` docs (§26, §29 #9). No prose lives outside this structured set;
there is no separate doc-comment dialect to parse.

#### 30.6.2 Structured diagnostic suppression — Normative

Suppressing a diagnostic requires a reason, consistent with the project's
no-silent-silencing stance. The form is a row:

```
<subject> suppress <CODE> because "reason"
```

`because` is already reserved (§2). A `suppress` row without a `because` string
is itself a hard error, as is naming an unknown code.

**Deny vs advisory (WS2-072).** Only **advisory** diagnostics (tier T3/T4) may be
suppressed. A **deny-tier** code — T0/T1/T2, i.e. the soundness/UB, memory-safety,
security-sink/secret, and structural invariants — is **non-suppressible**: a
`suppress` of one is itself a hard error (SS5402) and the underlying diagnostic
stays in effect. You fix the cause, you do not silence it. (Every registry code
carries a tier, so the deny set is exhaustive.)

Suppression is scoped to the **subject entity and the one
named code**; there is no file-wide or wildcard suppression. For an `operation`
subject, that scope covers diagnostics attributed to the operation's own rows —
its steps, `let`/declaration rows, and `at` labels — but **not** diagnostics
attributed to a separately-declared `call`/`task`/`cleanup` entity it activates:
those are their own subjects and carry their own `suppress` row. Every silenced
check stays visible, greppable, and justified.

### 30.7 Grammar and reserved-word additions

These tokens are introduced by §30 and must be absorbed by the §2 reserved set
(the change protocol requires §2/§5/§17 to move with this section):

- **Declaration predicates:** `forTarget`, `forPlatform` (§30.3.1), `suppress`
  (§30.6.2).
- **Mode value:** `capturedOutputReplay` (§30.1.1 — already present as a `mode`
  value, now defined).
- **Literal class:** duration literals `<integer><unit>`,
  `unit ∈ {ns,us,ms,s,m,h}` (§30.1.2).
- **Annotation (roadmap):** `export c` (§30.4.2).

`because` and `target` are already reserved and are reused, not added. §30 adds
no control-flow guard: variant dispatch is owned by §10.5/§13.

---

## 31. Implementation layering and prototype freeze

This section is **informative** — a build plan, not language spec. The syntax
surface is now broad enough that the next useful work is *implementation*, not
more grammar. The risk has shifted from "is the design coherent?" to "prototype
scope explosion." This section recommends freezing the surface and prototyping
in layers. It is a companion to §29: §29's waves close *spec* gaps; these layers
stage the *build*.

### 31.1 Freeze the syntax surface

For the prototype, treat the core surface as **frozen**: §§1–17 (grammar,
entities, control flow, calls/tasks/cleanup, islands, lints), §22–23 (canonical
ordering, compact profile), and the §30 resolutions. Remaining improvements
should be implementation-driven — convert one real handler, format that subset,
and see whether agents can patch it with `sem slice`/`sem doctor`. Resist new
grammar until the prototype shows a concrete need; the standout primitives
(`call`/`task`/`cleanup` split, goto substrate, `ifVariant` narrowing,
compiler-derived construction/access targets) are settled enough to build on.
(§33's gap resolutions and §34's minimal-core *direction* post-date this freeze:
§33 are the final closing additions to the frozen surface; §34 is a v0.4 target,
not a v0.3 change — neither reopens §§1–17 for the prototype.)

### 31.2 Layers

Implement in order; each layer is runnable before the next begins.

**Layer 1 — core executable language.** entity/fact/step rows; `operation`/
`call`/`task`/`cleanup`; `let`; `branch`/`goto`/`return`/`at`; `error`/
`errorCase`; `record`/`enum`/`alias`; `capability`/`effect` rows; basic lints
(unknown predicate, arity, unresolved reference). *Goal: programs compile and
run.*

**Layer 2 — formatter + codemod.** current→EAV lowering; canonical ordering
(§22); non-canonical sugar lowering (§13 `else`/`ifOut`/`ifValue`, compound
`defer`, `call async yes`); deterministic generated names (§13/§15.6);
idempotency (`fmt(fmt(x)) == fmt(x)`, §29 #11); row-count measurement (§21).
*Goal: one canonical form; both surfaces map to it.*

**Layer 3 — semantic safety.** ownership/cleanup lints (§15/§15.6);
task-lifecycle lints (§13); effect/capability union (§15); `ifVariant` narrowing
+ exhaustiveness (§13, §17 #52–53); return arity (§13). *Goal: the safety
contract is enforced, not just described.*

**Layer 4 — stdlib / signatures / security (later).** `intrinsic` signature
modules + `.semsig` (§26); `trustConstraint` (§16/§26); dependency effect surface
+ `build.sem.lock` + supply-chain/capability-allowlist checks (§28); HTML
`HtmlTrustedFragment` enforcement (§16). *Goal: the ecosystem and supply-chain
guarantees.*

### 31.3 Prototype scope cap

To stop the manifest from becoming a second language before the core runs, the
v0.3 **prototype** treats the build/dependency surface (§28) as **parse-only**:
`build.sem` and `build.sem.lock` rows parse and shape-validate, but resolver
semantics — MVS, git fetch, digest verification, and capability-allowlist
enforcement (§28.4/§28.5) — are deferred to Layer 4. Likewise the deferred
language features (§27: collections, generics, loops, concurrency primitives,
retry/timeout, FFI ABI) stay out of the prototype; their §27 interim patterns
(opaque handles + goto loops, hand-monomorphization, cooperative `task`) carry
the worked-example class.

### 31.4 DevX is mandatory, not optional

The language is row-heavy and semantically rich; it only *feels* good if agents
operate through **semantic commands** and inspect EAV slices only when needed.
The target loop:

```bash
sem doctor OP                          # what's wrong / missing
sem slice OP --for-edit add-cleanup    # the minimal neighborhood to edit
sem add cleanup ...                    # structured edit, signature-checked
sem check                              # prove semantic state
sem explain OP                         # read back control/effect/cleanup summary
```

So `sem slice`/`sem explain`/`sem doctor`/`sem add` (§24, proposed) move from
nice-to-have to **required at Layer 1+** — a human or agent should rarely hand-edit
raw canonical EAV. This is the bet that makes verbosity acceptable: the rows are
the compile target and the diff format, while the *authoring and editing* surface
is semantic commands and the compact profile (§23).

### 31.5 Validation milestone

The single most informative next step is not more spec: take one real handler
(e.g. `healthHandler`, §19), run the current→EAV conversion (§20), implement
Layer 2 canonical formatting for just that subset, and measure whether an agent
can patch it (add a route, add a cleanup, add an `ifVariant` arm) using
`sem slice`/`sem doctor`. That answers the §21 adoption gate and the §29 #16
human-authoring question with evidence instead of argument.

---

## 32. Implementation-grade semantics and tooling notes

This section is **informative**. It decomposes the §29 headline gaps into the
**precise sub-rules an implementer must pin** — the level below "this gap exists."
Each item names its owning section and §29 gap; the bullets are the open
decisions. **The item numbers below are the review's checklist (1–23), not §29.1 register
numbers** — each cites its §29 gap explicitly. The two previously-untracked items,
ownership edges (item 9) and semantic diff (item 23), are now register gaps **§29
#26** and **#27**. This is a checklist, not a second register — dispositions stay in
§29.

### 32.1 Language semantics

1. **Lowering model** — §29 #3 (keystone). Pin: whether EAV shares the current
   `semsc.py` AST; which compiler structures change; EAV-as-prenormalization vs a
   second front-end. Everything else here depends on this.
2. **Canonical formatter semantics** — §29 #11. Hard contract: total, idempotent
   (`fmt(fmt(x)) == fmt(x)`), order-stable (§22), stable generated names
   (§13/§15.6), trailing-comment preservation (§2).
3. **Control-flow edge semantics** — §13, §29 #2. Pin: defers run only at
   `return`, not at a `goto` that stays in the operation; an unreachable label is
   dead (SS1012); no implicit fallthrough — an `at` block ends at the next
   `return`/`goto`/`at`; binding availability follows branch dominance; cleanup
   order is reverse-registration on every exit path (§15.6).
4. **Path-sensitive binding rules** — §25, §29 #2. Pin: an `out` binding is live
   only on the non-error continuation after `do`/`join`; a `catch` var only on
   `ifError`/`ifVariant` target paths; a binding not yet produced on an
   early-exit path is unbound (referencing it is a hard error); an uninitialized
   `let mutable` is unbound until its first `out` rebind.
5. **Error propagation** — §13, §29 #2(d). `onFailure propagate` is unspecified
   on conflict: decide whether a cleanup error **replaces** the in-flight error or
   **wraps** it with a `causedBy` provenance field. v0.3 punts chaining; this must
   be decided before `propagate` ships.
6. **Effect/capability closure** — §15 (effect-union), §29 #10. Exact algorithm:
   an operation's effect set = its own `effect` rows ∪ the effects of every
   `do`/`start`/`defer`-activated call/task/cleanup, taken transitively through
   user-operation `invokes`; each effect must be covered by a `uses` capability
   whose `grants` matches action+resource; an uncovered effect is reported against
   the owning operation.
7. **Trust enforcement** — §16/§26, §29 #10/#19. Pin: how a URL-bearing hole is
   identified (the `href`/`src`/`action`/`formaction`/`poster` allow-list); how
   `trustConstraint arg SLOT TYPE` is checked at the producing call; and that
   `HtmlTrustedFragment` provenance is convention, not static proof, in v0.3.
8. **Managed value lifetime** — §10.6, §29 #14. Source contract is fixed (value
   semantics, no free/GC). Pin the *backend* strategy per kind — `String`,
   `record`, enum payload, primitive: copy vs move vs immutable-share, and whether
   returns are copied or moved out.
9. **Resource ownership semantics** — §15/§15.6, §29 #26. Pin:
   one `owns` per acquisition (no aliasing an owned handle into a second binding);
   passing an owned handle as an `arg` does **not** transfer ownership unless the
   callee signature declares `owns` (explicit transfer); registering a handle's
   cleanup twice is a hard error (double-cleanup); an owned handle may not escape
   via `return` unless the operation's `out` type carries the cleanup obligation
   to the caller.
10. **Enum payload access / narrowing** — §13 `ifVariant`, §17 #52–53. Mostly
    specified; pin: `bind PAYLOAD` is in scope only on the matched label's path
    (catch-style, §25); a shared failure label reached from several `ifVariant`
    arms sees only the bindings common to all of them; exhaustiveness is over the
    variant-test series (§13).

### 32.2 Spec artifacts

11. **Formal grammar** — §29 #1. EBNF + token classes + island enter/exit/dedent
    rules + an invalid-example corpus. (Precedence is N/A — no expressions.)
12. **Diagnostic registry** — §29 #12. One canonical `SSxxxx`/`MDxxxx` table:
    code → meaning → severity/tier → repair → example. Today codes are scattered
    across §17/§24.
13. **Conformance test matrix** — §29 #6. Parser, formatter round-trip, linter
    fixtures, lowering, editor, and migration goldens; honor "no Impl'd without a
    test that fails under a no-op lowering."
14. **Normative vs informative split** — §29 #13. Label every section
    *Normative* / *Informative* / *Roadmap*. As a baseline: §§1–17, 22–23, 30 are
    normative; §§24, 28(resolver), 29, 31, 32 are informative/roadmap.
15. **Migration correctness contract** — §29 #4. The current→EAV→current
    round-trip guarantee, an enumerated list of lossy cases and unsupported edges,
    and codemod acceptance criteria stated as *semantic equivalence* (not row
    count, which is §21).
16. **Version / rollout contract** — §29 #8. Feature flags, compatibility mode,
    deprecation timeline, and the exact gate (beyond §21's metrics) at which EAV
    becomes the mandatory authoring surface.

### 32.3 Tooling

17. **Exact `sem` tool contracts** — §29 #5, §24. Per command: `argv`, JSON schema
    (extend the existing `sem.*.v1` surfaces), exit codes, and MCP tool mapping —
    not new schemas invented from scratch.
18. **`sem slice` contract** — §24, §29 #5. Define what a slice includes (the
    operation + its activated `call`/`task`/`cleanup` entities + referenced
    types/capabilities), how minimality is measured, and the guarantee that an
    edit confined to a slice keeps the slice independently `check`-able.
19. **`sem doctor` / `sem add` contract** — §24, §29 #5. `doctor`: precondition
    (file parses) → severity-grouped diagnostics + suggested `sem add` argv.
    `add`: signature/arity checked *before* insert; failure modes = refuse on type
    mismatch or ambiguous target (never insert an invalid row).
20. **Semantic patch validation** — §29 #5/#15. Formal loop:
    `check` → `fix --plan`/`doctor` → `patch` (dry-run, then apply) → `check`;
    stale-file behavior = refuse to apply against a changed mtime/digest (the same
    protection that guards in-place edits to this very document).
21. **Diagnostic source mapping** — §29 #15. A diagnostic computed on canonical
    EAV must map back to the author's compact/current source span; the lowering
    (§29 #3) carries a row↔row map so the user sees the line they wrote.
22. **Editor / LSP plan** — §29 #7. Semantic tokens (the col-1-subject /
    col-2-predicate shape is a tokenization advantage), hovers (from §6 metadata),
    completions (from the §5 per-kind predicate vocabulary), rename
    (entity/binding), symbol index, diagnostics (mapped back, item 21), and code
    actions that apply `sem add`/fix.
23. **Semantic diff** — §29 #27. A row-aware diff reporting
    *typed* deltas instead of text: "operation X added effect Y", "cleanup Z
    removed", "route changed", "capability added", "return arity changed". The EAV
    row model makes this natural — each row is a typed fact, so a diff is a set of
    fact changes. Feeds code review and the §28.5 supply-chain
    capability-change surface (a dependency that newly requests an effect is a
    semantic-diff finding).

---

## 33. Core gap resolutions (v0.3 simple profile)

**Normative.** This fills the remaining unacknowledged gaps with the *simplest
safe, performant* resolution: output stays **safe** (a trap beats undefined
behavior), **performant** (no hidden machinery, no allocation on the common
path), and **simple** (no new conceptual weight). Where a feature would add
complexity, v0.3 **declines** it and gives the simple alternative. Lexical
additions here must be absorbed by §2/§16 (single source of truth), as §30.7
requires.

### 33.1 Literal grammar completion — Normative

- **Hex and binary integer literals.** `0x` + hex digits and `0b` + binary
  digits, valid in any integer position, typed like decimal (§33.6). For `repr`
  discriminants, bit flags/masks (§10.6 has bitwise ops but no way to *write* a
  mask today), and ABI constants. **No octal** — the leading-zero form is an
  error-prone footgun; write `0x`.
- **Digit separators.** A single `_` *between* digits is ignored: `1_000_000`,
  `0xFF_FF`. Leading, trailing, or doubled `_` is a parse error.
- **Hex byte escape `\xNN`.** Exactly two hex digits, emits one raw byte — the
  only way to author a non-ASCII byte in a bytewise-UTF-8 `String` (§10.6).
  `\u{…}` codepoint escapes are deferred to i18n (§29 #22); `\0`/`\r` stay banned.
- **No character literal.** A byte is an integer literal of type `Byte`/`UInt8`
  (`0x41`); text is a `String`. This avoids a second quote character — hex
  literals already cover the byte-authoring need.

### 33.2 Source file format — Normative

Source is **UTF-8, no BOM**. Line endings may be LF or CRLF; CRLF is normalized
to LF on read (so the `\n`-only string rule, §2, is unaffected). **Island
indentation (§16) is spaces only** — a tab in island indentation is a hard error,
so dedent is unambiguous: an island body line belongs to the island while its
indentation is deeper than the `body` row, and the island ends at the first line
indented at or below the `body` row, or any column-1 token row. (Closes the §29
#1 island-dedent sub-gap.)

### 33.3 Recursion — Normative

A user operation **may** call itself directly or mutually (via `invokes`, §15) —
ordinary call nesting, no special syntax. Unbounded recursion exhausts the stack
and **traps** (§10.6): safe, never silent corruption. Bound depth with `memory
stack <bytes>` (§11). Tail-call elimination is a permitted backend optimization,
**not a guarantee** — do not write recursion that *requires* TCO to avoid a trap.

### 33.4 Compound conditions — Normative

There are no `and`/`or` operators (no expressions). A compound condition is
sequential guards — this is the canonical form, so agents emit it consistently:

```sem
# A and B — proceed only if both true
op branch ifFalse condA goto failLabel
op branch ifFalse condB goto failLabel

# A or B — proceed if either true
op branch if condA goto okLabel
op branch if condB goto okLabel
op goto failLabel
op at okLabel ...
```

Each guard is a branch, so this short-circuits naturally and is exactly as
performant as the branches it compiles to. No new syntax.

### 33.5 Numeric conversion semantics — Normative

`convert.*` is explicit; there is no implicit coercion (§10.6). Default behavior
is safe and deterministic:

- **float→int truncates toward zero**; NaN or out-of-range **traps**.
- **narrowing int→int** that would lose value (out of target range) **traps**;
  widening is exact.
- **int→float** rounds to nearest, ties to even (IEEE-754).

Default = trap on loss (safe). Callers that deliberately want wrap or saturate
use explicit stdlib variants (`convert.*Wrapping` / `*Saturating`, External
surface §27) — the core conversion stays simple and safe by default.

### 33.6 Literal width — Normative (resolves the §2/§10 tension)

An integer or float literal **takes the type of its annotated position** — the
declared type at a typed `let`, `arg`, `field`, or `return` — and the compiler
**range-checks it at compile time**; out of range is a hard error. So `let
okStatus immutable HttpStatusCode 200` is valid (200 fits the `Int32` base). The
"default `Int64`" rule (§2) applies only to a literal with *no* annotated type.
Literals are **range-checked annotations**, not `Int64` values needing a
conversion call: this supersedes the "narrowing needs a conversion call" wording
in §2 *for literals* (it still holds for **bindings**/computed values, §33.5).

### 33.7 Record equality and layout — Normative

- **Equality.** `equals`/`notEquals` (§13) accept `record` operands as
  **fieldwise equality** — each field compared by its own value rule (deep for
  `String` and nested records), recursively. Ordering (`greaterThan`/`lessThan`)
  on records stays invalid (§17 #45). Simple, safe, and what callers expect.
- **Layout.** Record field layout (order, padding, alignment) is
  **compiler-chosen and not source-controllable** in v0.3 — the compiler may
  reorder/pad for size or speed. There are no `recordLayout`/`recordAlign` rows
  (the v0.1 forms are dropped). ABI-stable layout for FFI is deferred with the
  FFI type-mapping (§27/§30.4); ordinary records make **no** layout promise.

### 33.8 Trap during cleanup — Normative

§15.6 routes a cleanup *call* that returns an **error** via `onFailure`. A
cleanup that **traps** (e.g. div-by-zero, §10.6) while unwinding is **fatal**:
the process aborts immediately, no further deferred cleanups run, and the
diagnostic names both the in-flight trap/return and the cleanup trap. Unwinding
stays bounded and state stays well-defined — there is no trap-recovery machinery.

### 33.9 Operation references — Normative (function pointers, not closures)

The one structural hole — passing *behavior* (a comparator, a handler) — is
filled with the simplest safe primitive: **a typed reference to a named
operation. No closures, no captured environment.**

Declare the signature with an `operationType` entity (§5/§2):

```sem
LessThanInt64 is operationType
LessThanInt64 in left Int64
LessThanInt64 in right Int64
LessThanInt64 out Bool
```

A value of that type is a **named operation** whose `in`/`out` match exactly:

```sem
sortTasks arg compare LessThanInt64 ascendingById   # ascendingById is an operation
```

Invoke it indirectly by naming the **binding** (not a target path) in `invokes`;
the linter checks the binding's `operationType` against the call's args/out:

```sem
runCompare is call
runCompare in sortTasks
runCompare invokes compare        # `compare` is an operationType binding
runCompare arg left Int64 leftItem
runCompare arg right Int64 rightItem
runCompare out isLess Bool
```

That is a function pointer: one indirect call, no allocation, no capture — safe
and performant. **Closures are declined** — capturing local state would add
lifetime/escape complexity (§32.1 #9); behavior that needs state passes the state
as ordinary `arg` data, or reads it through a capability (§8). This unblocks
comparators, event handlers, and (later) `each` over collections.

Resolution rule: when an `invokes` target names an in-scope `operationType`
binding it is an indirect call; if a name matches both a local binding and a
module operation, the local binding wins and the linter warns to rename.

### 33.10 Absorption and register

The lexical rules (§33.1–§33.2) are absorbed into §2 (hex/binary/`_` in **Integer
literals**, `\xNN` in **String literals**, islands-spaces in §16). `operationType`
(§33.9) is in §2's reserved entity-kind names **and** now has its §5 predicate-table
row (`is in out`).
These resolutions **close** blind spots that were never in the §29 register; the
only residual is operation-reference *lints* (signature match, indirect-call
arity, the bind-vs-operation name rule) — Layer-3 work (§31). Declined-by-design
here, recorded so they are not mistaken for oversights: octal literals, character
literals, `\u{}` escapes (→ i18n), source-level record layout, closures, and
guaranteed tail calls.

---

## 34. Minimal-core keyword profile — Normative direction (v0.4)

§2 is the **full profile**: it makes every domain contract a first-class keyword.
Maintaining it has proven costly — by the Change Protocol, the parser, linter,
formatter, editor grammar, and docs must move in lockstep for *every* token, and
most of that surface is domain vocabulary, not language. This section defines the
**minimal-core profile**, the v0.4 target: the smallest keyword set that keeps the
language's guarantees, with everything else expressed as operations, records,
capability values, and signature-checked stdlib calls. §2's full set stays valid
until the domain sections migrate (§34.5); this section governs the direction.

### 34.1 What survives as a keyword

A token is a **core keyword** only if it meets one of three tests:

- **(a) Primitive of the tape, control, binding, or type system** — the parser or
  evaluator cannot express it as data or a call (no bootstrap): row/entity shape,
  control flow, result binding, and type *declaration*.
- **(b) The security boundary** — the effect/capability check, kept built-in so
  that safety never depends on an external `.semsig` being present and honest.
- **(c) The `call`/`task`/`cleanup` split** — **preserved verbatim.** The
  one-verb-one-kind mapping (`do`→`call`, `start`→`task`, `defer`→`cleanup`, §13)
  is the agent-safety property reviewers singled out; collapsing it to
  `call`+attributes would re-introduce the activation ambiguity it removed. The
  split's three kinds, its activation verbs, and the ownership/cleanup contract
  that gives the `cleanup` kind meaning are all kept even though pure minimization
  would fold them away.

Everything that fails all three tests is **demoted** (§34.3). A domain contract
checked by a `.semsig` signature is exactly as statically checkable — and just as
greppable — as one checked by a keyword; the keyword bought only parse-vs-lint
timing and shadow-protection, which do not justify the lockstep maintenance cost.

### 34.2 The core keyword set

```
tape / declaration    is
kinds                 operation  call  task  cleanup  record  enum  alias  storage
type structure        field  variant  for  operationType
signature / dataflow  in  out  catch  invokes  arg  discards  let  mutable  body
control flow          do  branch  goto  return  at
async lifecycle       start  join  poll  cancel  detach        (the task half of the split)
cleanup               defer  owns  cleanedBy  cleans  onFailure  because   (the cleanup half)
guards                if  ifFalse  ifError  ifVariant  ifReady  ifPending  ifCanceled  else  bind
security boundary     effect  uses  capability  grants          (rule b)
module wiring         module  imports  exports
literals              nil  true  false
primitive types       Int8…Int64  UInt8…UInt64  Float32  Float64  Bool  String  Void  Byte  Result
```

~50 reserved words + the type names, down from ~115 — and because `enum` is a sum
type it now covers errors, so `error`/`errorCase`/`of`/`payload` are gone. This
table is the governing set of *categories*; §5 stays the authoritative per-kind
predicate list (minus the rows §34.3 demotes).

- **Guards stay split between lifecycle and value.** `ifError`/`ifReady`/
  `ifPending`/`ifCanceled` test the runtime state of a `call`/`task` (part of the
  split, rule c) and `ifVariant` is the data-inspection primitive (§13) — all
  kept. `ifOut`/`ifValue` and the comparators are **not** (§34.3).
- **`branch` is retained** for readability even though `if … goto` alone suffices
  — the one concession to ergonomics over strict minimality.

### 34.3 What demotes, and to what

| Full-profile keywords | Minimal-core form |
|---|---|
| `webServer` `host` `port` `route` `startup` `shutdown` `notFound` `methodNotAllowed` `middleware` | an `HttpServer` **record** (field names) + `http.route`/`http.serve` **calls**, checked by `standard.http`'s `.semsig` |
| `htmlTemplate` `body`(`html`/`sql`/`json`) | a `String`/`storage` value + `html.render`/`sql.exec` **calls**; the template is data |
| `error` `errorCase` `of` `payload` | `enum` + `variant` |
| `equals` `notEquals` `greaterThan` `lessThan` · `ifOut` `ifValue` | `compare.*` **calls** returning `Bool`, then `branch if` |
| `purpose` `invariant` `note` `rationale` `risk` `example` `tag` `deprecated` `owner` | **typed comments** (`# purpose:` …) — non-executable |
| `project` `target` `entry` `mode` `languageVersion` `toolchain` `require` `replace` `allowEffect` `platform` `constant` `configure` `native*` `os` `arch` `targetRuntime` `output` `override` `forTarget` `forPlatform` `resolved` `toolchainResolved` `effectSurface` | a **build record** + `standard.build` API; `build.sem`/`build.sem.lock` are data in the same tape |
| `intrinsic` `semsig` `version` `generatedBy` `describes` `target`(pred) `trustConstraint` | the `.semsig` sidecar signature format (tooling), not source keywords |
| `suppress` `export`(`c`) `using` `repr` | `# suppress:` typed comment · FFI-export sidecar · folds away with capability values · `# repr:` / construction arg |

A demoted contract is **not weaker**: `http.route`'s arity and types are checked
by `standard.http`'s `.semsig` exactly as a `route` keyword would have been, and
`grep "http.route"` finds every route just as `grep " route "` did.

### 34.4 The split, restated (do not collapse)

Three activation verbs map one-to-one to three kinds; the linter rejects any
cross-use:

```
do <call>                              — synchronous invocation
start / join / poll / cancel / detach <task>   — async lifecycle
defer <cleanup>                        — scope-exit cleanup
```

This is rule (c) and is **not** subject to minimization. The ownership/cleanup
contract (`owns`/`cleanedBy` on the producer; `call`/`cleans`/`onFailure`/
`because` on the `cleanup` entity) is kept with it, because it is what makes the
`cleanup` kind more than a deferred `call` (§15.6).

### 34.5 Migration status

§2 (full profile) stays authoritative until each domain section is migrated.
Order: §14 `webServer` → `standard.http` record + calls; §16 islands →
`html.render`/`sql.exec`; §8 capability surface reviewed against rule (b); §28
manifest → build record; §6 metadata → typed comments. Each migration deletes its
keywords from §2 and adds the equivalent `.semsig` signatures. The split (§34.4),
the security boundary (§34.1b), and the tape/control/type primitives never
migrate.
