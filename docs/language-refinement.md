# Language refinement notes

Status: design accepted by the project owner on 2026-11-13 (P-1, P-2, and
LR-01 through LR-23, with LR-19 superseded by LR-20). Part 2 (LR-24 to LR-41)
and Part 3 (LR-42, amendments after an adversarial review) were added
afterwards by delegation and have not been reviewed by the owner. Part 3
overrides earlier text where they conflict. Parts 4 to 6 record the
implementation, which started the same day: Part 5 removed the bridge to the
earlier compiler and dropped backwards compatibility at the owner's request, and
Part 6 removed the earlier compiler.

**This file is the language's normative design.** With the earlier compiler and
its spec removed (Part 6), the decisions here, the shape table
(`semanticscript/compiler/refined/shapes.py`, rendered as
`docs/refined-grammar.md`), and the checker together define the language.
Started: 2026-11-13. Baseline: `main` at `b6aa5c7`. Section references written
as `§n` point to `docs/LANGUAGE.md` as it was at that commit (removed in Part 6;
still in git history).

## Purpose

A place to collect and settle changes to the language itself: syntax, scoping,
typing rules, and the effect model. Compiler and tooling defects go in GitHub
issues; they appear here only when the fix is a language rule.

## How to use this file

Each item has an id (`LR-nn`), a status, and four parts:

- **Problem**: what hurts, in one or two sentences.
- **Evidence**: a program, measurement, or spec section that shows it.
- **Options**: the candidate changes, with their costs.
- **Decision**: empty until we agree. When decided, add the date and move a
  one-line summary to the decision log at the bottom.

Statuses: `open` (not discussed), `discussing`, `decided`, `dropped`. A decided
rule is implemented when the checker enforces it; Part 5 lists what is
enforced.

"Leaning" marks a preference from the review, not a decision.

Worked examples anywhere in this file follow the full skeleton from LR-18,
LR-20, LR-30, and LR-31, as amended by Part 3. The complete examples are the
projects in `docs/refined-examples/`, checked by the refined front end (Part 4).

"By delegation" marks a decision made on behalf of the project owner from P-1
and P-2, after the owner asked for design questions to be decided that way.
Any of them can be overturned; record the reversal in the decision log.

## Principles (decided)

- **P-1 Explicit over terse** (2026-11-13). Source is verbose and 100% explicit.
  Agents write the code, so the human preference for implicit forms is ignored.
  Row count is not a cost we optimize.
- **P-2 Explicit construction is enforced** (2026-11-13). Nothing is implied and
  every stated fact is checked. Concretely:
  1. No defaults. A fact that affects meaning must be written; a missing row is
     an error, not a default.
  2. Fixed shape. Every predicate has an exact token count and a token class or
     closed value set per position. Extra, missing, or out-of-set tokens are
     errors.
  3. No silent duplicates. A single-valued fact appears exactly once.
  4. No unchecked statements. If a row states a type, effect, owner, or name, the
     compiler verifies it against the rest of the program.

## Constraints we keep

- One row shape: `<subject> <predicate> <payload>`. No nesting, no expressions.
- The split (`do` → call, `start` → task, `defer` → cleanup) stays (§34.4).
- Effects, failures, cleanup, memory, and authority stay source data.
- §34 (minimal core) is the direction. A refinement should shrink or hold the
  keyword set, not grow it, unless it removes more than it adds.
- Every change moves spec, grammar, compiler, tests, and editor together
  (the change protocol in CONTRIBUTING.md).

## Items

### LR-01 Call declarations sit far from the steps that use them

Status: decided

- **Problem**: An operation's step list says `do recCall`, but the call's target,
  arguments, and outputs are declared in a separate entity elsewhere in the file.
  Reading one operation means jumping between its steps and every call it uses.
  Flat is not the same as local.
- **Evidence**: `examples/factorial.sem`: `factorial` has 5 steps and 4 call
  entities declared after it. `branch if isBase` uses a name that only appears as
  an `out` row on `baseCheck`.
- **Options**:
  1. Keep the model; make canonical ordering (§22) place each call entity
     directly after its first use, and have `fmt` enforce it.
  2. Allow an inline step form for single-use calls, as non-canonical sugar that
     `fmt` expands (same mechanism as `ifOut`, §13).
  3. Leave source as is and rely on tooling (`slice`) for the local view.
- **Decision** (2026-11-13, by delegation): option 1. No inline form, because P-1 allows one
  spelling per fact. Canonical order (§22) places each call, task, and cleanup
  entity directly after its owning operation, in order of first use.
  `fmt --check` is part of the strict gate, so non-canonical order is an error.

### LR-02 Call and task names are global

Status: decided

- **Problem**: A call is tied to its operation by an `in` row, but its name lives
  in one program-wide namespace. Every call in a program needs a unique name.
- **Evidence**: Names like `setMeDisplayNameCall` in
  `apps/taskforge-web/src/main.sem`. Two modules with a private `helper` fail to
  compose when the second owns calls. The SSRF and path-traversal validators can
  be bypassed by declaring the same binding name in another operation.
- **Options**:
  1. Scope call, task, cleanup, and binding names to their owning operation.
     Rows keep the same shape; resolution becomes `(operation, name)`.
  2. Keep global names but require an operation prefix by convention and lint it.
- **Decision** (2026-11-13, by delegation): option 1. Call, task, cleanup, label, and binding
  names resolve as `(owning operation, name)`. The owner is already explicit in
  the required `in` row, so nothing becomes implicit. Two operations may reuse
  a name; within one operation a name is unique across all of those classes.

### LR-03 Row count for ordinary programs

Status: dropped (P-1: verbosity is intended; none of the options below apply)

- **Problem**: Simple programs take many rows, which costs reading time for
  people and tokens for agents.
- **Evidence**: hello world is 31 lines; recursive factorial with three
  assertions is 127; `taskforge-web`'s main file is 4,674 lines for 18
  operations. §21 already defines a row-count adoption gate.
- **Options**:
  1. Make more metadata optional on private entities (`memory`, `async`,
     `purpose`, `invariant`) with documented defaults.
  2. Drop restated facts (see LR-05).
  3. Promote the compact profile (§23) to the authoring default and treat the
     canonical form as what `fmt` and tools produce.
- **Decision**:

### LR-04 Scope at a label depends on which jumps reach it

Status: decided

- **Problem**: Control flow is `goto` only. Whether a binding exists at a label
  depends on the paths that reach it, and the language has no stated rule for it.
- **Evidence**: A value bound on one branch and used after a label that the other
  branch also reaches passes `check --strict` and then fails in LLVM. §25 (formal
  scope model) does not define definite assignment.
- **Options**:
  1. Add a definite-assignment rule to §25: a binding is in scope at a step only
     if every path from the operation's entry to that step binds it. Violations
     are a check error.
  2. Add the planned `repeat`/`each` sugar (§27) so most programs need fewer
     hand-written labels. This reduces the problem but does not replace option 1.
- **Decision** (2026-11-13, by delegation): option 1. §25 gains a definite-assignment rule: a
  binding is in scope at a step only if every path from the operation's entry
  to that step binds it; anything else is a check error. The same pass
  requires every path to end in a `return` whose value matches the `out` type.
  Option 2 is rejected as sugar (see LR-15). If iteration gets a construct, it
  is a real one designed under LR-10, with one spelling.

### LR-05 `arg` rows restate the type

Status: decided

- **Problem**: `arg left Int64 n` repeats a type the binding and the target's
  signature already fix. A restated fact can drift, and today the restatement is
  not compared with the binding's real type.
- **Evidence**: Passing an `Int64` binding in an `arg text String n` row is only
  rejected in code generation, with an LLVM-level message.
- **Options**:
  1. Keep the type token and make it a checked assertion: it must equal both the
     binding's type and the parameter's type.
  2. Make the type token optional; `fmt` fills it in for the canonical form.
  3. Remove it from `arg` rows.
- **Decision**: option 1, by P-1 and P-2.4 (2026-11-13). The type stays and is
  checked against both the binding and the parameter.

### LR-06 Prose contracts that are half-checked

Status: decided

- **Problem**: `purpose` and `invariant` are required English strings. One rule
  (SS1880) pattern-matches the English against the code, which makes ordinary
  wording a compile error.
- **Evidence**: "Always returns ExitCode 0" rejected the getting-started example
  and currently fails `apps/taskforge-tui`. §34.3 already plans to demote these
  rows to typed comments.
- **Options**:
  1. Follow §34.3: prose becomes typed comments, never checked.
  2. Split the two uses: free prose in comments, plus a small closed set of
     machine-checked contract rows (for example a `returns` fact with a literal).
- **Decision** (2026-11-13): neither option as written. `purpose` and
  `invariant` stay as rows, because they carry product context that code cannot
  express and rows travel with `slice` output where comments may not. This
  departs from §34.3, which demoted them to typed comments. The rules:
  1. **Where required.** `purpose` is required on entities that carry product
     meaning: operations, modules, capabilities, records, errors, and anything
     exported. `invariant` is required on operations only, because an invariant
     must be backed by a test (rule 3) and only behavior can be tested; it is
     allowed but optional elsewhere. Neither is required on calls, tasks,
     cleanups, or aliases of primitive types. (Narrowed 2026-11-13 while writing
     the worked example: a module or error invariant restates structure and
     would be filler under rule 5.)
  2. **`purpose` is declared intent.** The compiler treats it as narrative and
     never as fact. No rule reads its English.
  3. **`invariant` is a claim and must be checked** (P-2.4). Each invariant
     carries an id, and at least one test must reference that id. The compiler
     enforces that every invariant has a referencing test; it does not read the
     English.
  4. **Staleness.** When an entity's structural rows change and its `purpose` or
     `invariant` rows do not, tooling flags the entity for the author to
     re-confirm or rewrite the prose.
  5. **No filler.** Text that restates the entity name or is trivially short is
     an error.
  6. **SS1880 is removed.** No rule pattern-matches English against code.
- **Still to design**: the row shape for an invariant id and for a test's
  reference to it; how "re-confirmed" is recorded for rule 4; the threshold for
  rule 5.

### LR-07 Where a call target's effects are declared

Status: decided

- **Problem**: The language says no operation performs an effect it did not
  declare, but it does not say where the effects of a library target such as
  `console.writeLine` are stated for the static check.
- **Evidence**: An operation that calls `console.writeLine` with no `effect` and
  no `uses` row passes `check --strict`. The project's own negative example
  `capability_ungranted_use` is not blocked. Any `imports` row plus an unresolved
  `uses` name skips coverage checking.
- **Options**:
  1. Every callable target carries its effects in its signature (`.semsig`, §26).
     An operation's effective effects are its own plus those of everything it
     activates, and all must be covered by `uses`.
  2. Additionally require that every `uses` row resolves to a declared or
     imported capability; an unresolved name is an error, never a skip.
- **Decision** (2026-11-13, by delegation): both options. Every callable target states its
  effects in its signature. An operation's effective effects are its own plus
  those of everything it activates, transitively. Each must appear as an
  `effect` row on the operation and be covered by a `uses` row naming a
  capability that grants it. A `uses` name that does not resolve is an error in
  every mode, with or without imports.

### LR-08 Mutability vocabulary

Status: decided

- **Problem**: The spec says only `mutability mutable` storage may be reassigned,
  but the value set for the row is not closed.
- **Evidence**: `mutability constant`, `mutability Immutable`, or no mutability
  row all allow `set`.
- **Options**:
  1. Closed set `mutable | immutable`, default `immutable`, anything else is a
     parse error.
- **Decision**: closed set `mutable | immutable`, and the row is required with no
  default, by P-2.1 and P-2.2 (2026-11-13).

### LR-09 Per-predicate arity and value sets

Status: decided

- **Problem**: Rows are accepted with extra tokens, missing tokens, or values
  outside the intended set. A flat grammar is only uniform if every predicate has
  a fixed shape.
- **Evidence**: `main is operation extra junk`, `main async banana`, a one-token
  `effect` row, a call with no `in` row or two of them.
- **Options**:
  1. Give every predicate in §5 a schema: token count (or range) and an enum or
     token class per position. The parser enforces it from one table, which also
     drives the editor grammar and `GRAMMAR.md`.
- **Decision**: option 1, by P-2.2 (2026-11-13). The audit below measures how far
  the current compiler is from it.

### LR-10 Collections, loops, and generics

Status: decided (2026-11-13, by delegation; see LR-24 and LR-25 in Part 2)

- **Problem**: v0.3 has no collections, structured iteration, or type
  parameters (§27). Real programs reach for raw `c.malloc` and `c.fopen`, which
  sidestep the safety model the language is built around.
- **Evidence**: `check --strict` on `apps/taskforge-web` reports 14 raw-heap
  findings; `apps/taskforge-tui` uses `c.fopen` and `c.malloc`.
- **Options**: to be written. Starting points are the planned shapes in §27 and
  `design-bounds-carrying-buffers.md`.
- **Decision**:

### LR-11 Lexical edge cases

Status: decided

- **Problem**: A few lexical rules are unstated or inconsistent.
- **Evidence**: Tokens split on space and tab only, while blank-line detection
  uses Unicode whitespace, so a trailing non-breaking space becomes part of a
  name. `"x"y` splits silently into two tokens. Raw control bytes are allowed
  inside strings although the `\0` escape is rejected.
- **Options**:
  1. State in §2: source is UTF-8; the only whitespace is space and tab; any
     other whitespace or control character outside a string is an error; a string
     must be followed by whitespace or end of line.
- **Decision** (2026-11-13, by delegation): option 1 as written, plus: raw control bytes
  inside a string are an error (use `\xNN`), and a quote character anywhere
  but the first and last position of a token is an error.

### LR-12 Integer conversion and shift semantics

Status: decided

- **Problem**: The spec says conversions are checked and a trap beats undefined
  behavior (§33), but two cases are not pinned down.
- **Evidence**: `convert.toUInt32` of a negative `Int64` returns 4294967295
  instead of trapping. A shift by a computed amount of 64 or more yields an
  undefined value.
- **Options**:
  1. State in §33: signed to unsigned traps on a negative value at every width;
     a shift amount at or above the bit width traps (or is defined to yield 0 /
     sign fill; pick one).
- **Decision** (2026-11-13, by delegation): both trap. Signed to unsigned traps on a negative
  value at every width, including equal widths. A shift amount below zero or at
  or above the bit width traps. A trap is the only result consistent with §33;
  a defined-but-surprising value would be an implicit behavior.

### LR-13 Order of the §34 migration

Status: decided

- **Problem**: §34.5 lists a migration order, but several items above interact
  with it (LR-06 metadata, LR-07 capability surface, LR-09 predicate table).
- **Options**: to be written once the items above are decided.
- **Decision** (2026-11-13, by delegation): the enforcement plan below runs first. §34's
  keyword demotions then proceed in the §34.5 order, with two changes: the
  metadata step is cancelled (LR-06 keeps `purpose` and `invariant` as rows),
  and each demoted domain must arrive with a shape-table entry and a
  strict-clean example, so the audit gate covers it from day one.

### LR-14 The compact authoring profile

Status: decided

- **Problem**: §23 lets authors omit a row's subject and has `fmt` restore it.
  That is an implicit form, and it means every tool must accept two spellings
  of one program.
- **Decision** (2026-11-13, by delegation): removed. The canonical form is the only accepted
  source. §23 and the compact round-trip gate in §21 are deleted from the
  spec; the compiler rejects subject-less rows.

### LR-15 Non-canonical sugar forms

Status: decided

- **Problem**: Several forms are accepted as input and rewritten by `fmt`:
  the `ifOut`, `ifValue`, and `else` branch guards, the compound `defer`, and
  `async` on a `call`. Each is a second spelling of something the canonical
  form already says.
- **Decision** (2026-11-13, by delegation): all become errors. One spelling per fact (P-1). A
  one-time migration command rewrites existing sources to the canonical form
  before the compiler starts rejecting them; after that the rewrite code is
  deleted.

### LR-16 Branching: implicit fallthrough

Status: decided (2026-11-13, by delegation; amended by LR-18)

- **Problem**: Control flow has two implicit edges. A `branch` names only the
  taken target; the not-taken path is "the next row". A label can be entered by
  falling into it from the row above. Inserting or moving one row can change
  where control goes without any row saying so.
- **Evidence**: `main branch if flag goto skip` followed by unrelated rows; the
  else-path is positional. `main at base return one` in `examples/factorial.sem`
  is reachable only by jump, but nothing in the grammar says a label cannot be
  fallen into.
- **Proposal**: make an operation's steps an explicit control-flow graph.
  1. A block starts at the operation's first step or at a label and ends in
     exactly one terminator: `return`, `goto`, or `branch`.
  2. `branch` names both targets: `OP branch <guard> goto <label> else goto
     <label>`. No fallthrough out of a branch.
  3. Falling into a label is an error. The row before a label must be a
     terminator.
  4. Every fallible `do` is followed immediately by its `branch ifError`.
  5. A chain of `ifVariant` tests on an enum must cover every variant, or end in
     a branch whose `else` target is declared as the default.
  6. Every backward `goto` (a loop) belongs to an operation that states
     `maxIterations <n>` or `maxIterations unbounded` with a `because` reason.
  7. No structured loop constructs. Structured loops are a human reading aid;
     an explicit graph is the more exact form for agents and for the checker.
     This narrows LR-10 to collections and generics.
- **Why**: the source becomes the same graph the compiler lowers to, so
  definite assignment and return-on-every-path (LR-04) are exact, and a one-row
  patch cannot silently re-route control.
- **Decision**:

### LR-17 Concurrency: tasks that do not run concurrently

Status: decided (2026-11-13, by delegation)

- **Problem**: The source can state concurrency that does not happen.
- **Evidence** (compiler at `b6aa5c7`): `start` runs the task's call to
  completion on the spot and sets a state flag; `join` and `poll` only change
  the flag; `cancel` sets a flag after the work has already finished;
  `ifPending` is never true. `readShared`/`setShared ... protectedBy <token>`
  ignore the guard token. Real asynchrony exists separately as the
  `standard.async` library on a single-threaded libuv loop, unconnected to the
  `start`/`join` keywords. Under P-2 these are unchecked statements.
- **Proposal**: one honest model, in three layers.
  1. **Ownership of tasks.** A task is owned by the operation that starts it.
     On every path to a `return`, each started task has been joined or
     cancelled. The check uses the same control-flow graph as LR-16. `detach`
     is removed; long-lived work is started by an operation that itself lives
     that long.
  2. **Cooperative tasks on one thread.** `start` schedules the task on the
     event loop and returns. Other tasks run only at explicit suspension rows
     (`join`, `poll`, and awaiting library calls). Every point where other code
     can run is a row in the source. There are no data races in this layer, so
     `mutex`, guard tokens, and `protectedBy` are removed from the language
     rather than kept as no-ops.
  3. **Parallel workers without shared memory.** Real threads are isolated
     workers. A worker receives its inputs by value or by ownership transfer
     (`takesOwnership`), returns a value, and talks to others only through
     channels. A worker's `uses` rows list its capabilities at spawn, so a
     forked worker can do only what it was granted. No shared mutable state
     crosses a worker boundary; `sharedState` is per-thread.
  4. **Processes.** No `fork`. Starting another process is a library call under
     a `process.spawn` capability.
  5. **Until layer 2 exists**, the compiler rejects `task` entities and the
     lifecycle steps with a "not implemented" error instead of running them
     synchronously.
- **Why**: P-2 forbids statements the backend ignores, and code proven on a
  backend where races cannot happen would break silently when a concurrent
  backend arrives.
- **Decision**:

### LR-18 Uniformity: one shape, one word, one spelling

Status: decided (2026-11-13, by delegation)

- **Problem**: Reviewing the first refined example for how predictable it is to
  write and read (for a small or large model) found forms where meaning is
  carried by absence, by position, or by a word that means two things. Each one
  is a place where a model has to guess.
- **Evidence**: the sum-to-five example written for LR-16.
  - Empty sets are written by leaving rows out (no inputs, no result, cannot
    fail), while `memory heap no` and `async no` state their negatives.
  - Only the first row of a block names the block; the rest belong to it by
    position. The entry block has no name at all.
  - `in` means "owned by" on a call and "input parameter" on an operation.
    `out` means "return type" on an operation and "bind a result" on a call,
    with different token counts.
  - Yes/no facts are spelled `yes`/`no`; Bool literals are `true`/`false`.
  - With two-target branches, `ifFalse` is a second spelling of `if`.
  - `RESERVED_WORDS` has 218 entries, including `limit`, `value`, `type`,
    `error`, `output`, `owner`, `timeout`, `target`, and `scope`. A model will
    reach for those as variable names. Writing the example hit this with
    `limit`.
  - `maxIterations` sat on the operation, so with two loops it would not say
    which one it bounds.
- **Rules**:
  1. **Fixed skeleton.** Every entity of a kind carries the same header
     predicates in the same order. An empty set is written `none`:
     `main input none`, `printTotal out none`, `pastLimitCheck catch none`,
     `factorial effect none`, `factorial uses none`. The checker verifies each
     `none` (for example `catch none` against a target that cannot fail).
  2. **Every step row names its block.** All step rows have the shape
     `<operation> at <label> <step> <payload>`. The unlabelled step-row class
     is removed. The entry block is labelled `entry`. A block's rows are
     contiguous. This amends LR-16.1.
  3. **One word, one meaning.** On operations, parameters are `input <name>
     <type>` and the result is `output <type>`. `in` means only "owned by" and
     `out` means only "bind a result".
  4. **One boolean spelling.** Yes/no facts take `true` or `false`:
     `main async false`, `main memory heap false`. The spec allows only
     `yes|no` for `memory heap`, so it is a boolean like the others (settled
     2026-11-13).
  5. **`ifFalse` is removed.** Swap the two targets of `if`.
  6. **Only literals are reserved** (`true`, `false`, `nil`, `none`). Every
     position in a row has a fixed class from the shape table, so a name cannot
     be mistaken for a predicate.
  7. **Loop bounds attach to the block.** `<operation> label <label>
     maxIterations <n>` bounds how many times control may enter that block in
     one run of the operation; `unbounded` requires a `because` row. This
     amends LR-16.6.
  8. **No member-style dots in references.** A test names an invariant as two
     tokens: `verifies main sumIsFifteen`.
- **Measuring it**: these rules come from inspection, not from a measured
  perplexity. The plan gains an evaluation step: have a small and a large model
  write a fixed set of programs from the spec alone, and track the first-try
  `check --strict` pass rate and which rules they break.

### LR-19 Who frees ordinary values

Status: superseded by LR-20 (2026-11-13). The rule "an operation frees what it
made unless it returned it" survives; LR-20 makes the region a named, declared
owner instead of an unnamed per-call one.

- **Problem**: The spec splits memory into three tiers but only defines two.
  Stack locals are automatic. External resources and raw heap are author-tracked
  through `owns`, `cleanedBy`, `cleanup`, and `defer`, and the compiler checks
  them. Ordinary heap values (`String`, records, enums built at run time) are
  "compiler-managed" with the mechanism "deferred" (§10.6, §29 #14).
- **Evidence**: The runtime gives these values a "process-lifetime allocation
  model" (`ss_sqlite.c`, `ss_string.c`): strings from `string.concat`,
  `convert.toString`, and `sqlite.columnText` are allocated and never freed. A
  long-running server leaks on every request. `memory stack` and `memory max`
  rows may be omitted, in which case "the runtime default applies" (an implicit
  default under P-2).
- **Proposal**:
  1. Every operation has an implicit-free but explicitly declared region for the
     ordinary values it creates. The region is released when the operation
     returns. A returned value is moved into the caller's region.
  2. The declaration is a required row, for example `OP memory region
     perCall`, with `perCall` the only value until others are designed. An
     operation that creates no heap values states `OP memory heap false` and
     the compiler verifies it.
  3. `memory stack` and `memory max` are required rows or are removed; they do
     not default.
  4. Raw `c.malloc`/`c.free` stay available only to standard-library modules.
     Application code uses regions and owned resources.
- **Why**: deterministic, no garbage collector, no reference counts, and the
  rule fits in one sentence: an operation frees what it made when it returns,
  unless it returned it.
- **Decision**:

### LR-20 Explicit memory and ownership

Status: decided (2026-11-13, accepted by owner)

#### How it works at `b6aa5c7`

Three tiers. Stack locals are automatic. Resources (handles) are tracked with
`owns` + `cleanedBy` on the acquiring call, a `cleanup` entity, and a `defer`
step. Ordinary heap values (`String` and friends built at run time) are
"compiler-managed" and in practice never freed.

Probes against `check --strict`, mutating `examples/defer_ownership_release.sem`
(audit scripts since removed with the earlier compiler, Part 6):

| Probe | Result |
| --- | --- |
| `owns` + `cleanedBy` but no `defer` | rejected (SS1503) |
| `owns` with no `cleanedBy` | rejected (SS3900) |
| `cleans` a name no call `owns` | rejected |
| Return an owned handle | rejected (SS3044C: ownership cannot be returned at all) |
| Same cleanup deferred twice | rejected (SS3044B) |
| Use after `takesOwnership` | rejected (SS1564) |
| Store an owned handle in module storage | **accepted** (escapes its cleanup) |
| `defer` registered before the resource is acquired | **accepted** |
| A path returns before the `defer` is registered | **accepted** (leak on that path) |
| `takesOwnership`, old owner's cleanup still deferred | **accepted** (double release) |
| Cleanup worker call takes no argument | **accepted** (it cannot touch what it "cleans") |
| Owned handle passed to a call with no borrow or transfer row | **accepted** (lending is implicit) |

Other findings:

- `memory heap no` is checked against five target names only (`c.malloc`,
  `c.calloc`, `c.realloc`, `memory.allocateMemoryBytes`, `buffer.create`).
  `string.concat`, `convert.toString`, and every other allocating call pass.
  The row is also optional.
- Strings made at run time use a "process-lifetime allocation model" in the
  runtime: allocated, never freed.
- `borrows`, `mayEscape`, `takesOwnership`, `consumes yes`, `region`,
  `allocateIn`, and `releaseRegion` appear in no example, no app, and no
  standard-library module. Only three `.semsig` files mention `borrows`.
- The 29 `examples/defer_*.sem` files are one program under 29 names
  (`defer_memory_free`, `defer_region_release`, `defer_borrow_return`, ...). The
  "resource" in each is an `Int64` constant and the cleanup sets a module
  variable.
- The spec says raw `c.malloc`/`c.free` is never app source. `taskforge-web` has
  14 `c.malloc` calls and `taskforge-tui` has 4 plus 2 `c.fopen`; they are
  warnings.
- Transfer has two spellings (`arg ... consumes yes` and `takesOwnership`), and
  `borrows X` and `lifetime X` state the same fact twice.

#### The refined model

One rule: **every value that needs release has exactly one named owner at every
step, and every acquisition, loan, transfer, and release is a row.** The checker
follows each owned value along every path of the control-flow graph (LR-16).

1. **Three value classes, stated per value.**
   - *Plain*: numbers, `Bool`, and fixed-size records and enums. Copied. No
     owner.
   - *Region-owned*: every heap value (`String` built at run time, buffers,
     collections). Its owner is a named region.
   - *Operation-owned*: resources (files, databases, sockets). The owner is the
     operation, which must release it.
2. **Every call states the owner of its result.** One skeleton row replaces
   `owns`: `<call> ownedBy none | <region> | <operation>`. The checker verifies
   it against the target's signature. `ownedBy <operation>` requires a
   `cleanedBy` row (LR-31 allows `cleanedBy none` when every path gives or
   returns the value).
3. **Regions are declared entities with a stated lifetime.**
   ```
   scratch is region
   scratch in greet                # owned by this operation
   scratch strategy arena
   scratch capacity 4096           # bytes, or `unbounded` with a `because` row
   scratch released atReturn       # atReturn | atProcessExit
   ```
   `atReturn` means the compiler releases the region at every `return` of the
   owning operation. `atProcessExit` is the stated form of today's silent
   behavior and is only allowed on regions owned by the entry operation.
4. **Allocation is visible as an argument.** A target that allocates takes a
   `Region` parameter. There is no hidden allocator. To return a heap value, an
   operation receives the caller's region as an input and states
   `<operation> outputOwner <thatInput>`.
5. **Every parameter and argument states how the value is passed.**
   - Operation: `<op> input <name> <type> value | borrowed | owned`.
   - Call: `<call> arg <slot> <type> <value> copy | lend | give`.
   - The checker matches them (`copy`/`value`, `lend`/`borrowed`,
     `give`/`owned`). LR-31 adds a fourth pair for exclusive loans,
     `lendMutable`/`borrowedMutable`. This is the single spelling for transfer; `consumes yes`
     and `takesOwnership` are removed.
6. **Linear rule for operation-owned values.** On every path from acquisition
   to a `return`, the value is released exactly once, given exactly once, or
   returned as an owned output. Concretely:
   - A deferred cleanup must be registered on the success target of the
     acquiring call's `branch ifError`, before any other use, and on no path
     where the value was not acquired.
   - A value with a deferred cleanup cannot be given or returned. A value that
     is given or returned on some paths is released on the others by an
     explicit `do` of its release call.
   - The cleanup's worker call must take the cleaned value as an `arg ... give`.
7. **Ownership can be returned.** `<op> output <type>` plus
   `<op> outputOwner caller` hands a resource to the caller, whose call row must
   then state `ownedBy <callerOperation>` and a `cleanedBy`. This removes the
   reason apps reach for raw handles.
8. **Borrowed values stay put.** A `borrowed` input or a view cannot be stored,
   returned, or given. A view names its source with one row, `borrows <value>`;
   `lifetime` and `mayEscape` are removed because a view may never outlive its
   source.
9. **No owned value in module storage.** Module storage and shared state hold
   plain values only. Long-lived resources are owned by the entry operation and
   lent downward.
10. **`memory heap` is checked exactly.** `true` if and only if the operation
    owns a region or receives one. `memory stack` and `memory max` are required
    rows.
11. **Raw allocation is an error in application source.** `c.malloc`, `c.free`,
    `c.fopen` and the pointer primitives are usable only inside standard-library
    modules, which wrap them as region-taking or resource-returning operations.

#### Worked example

```
greet is operation
greet purpose "Build a greeting for one name"
greet invariant startsWithHello "The result starts with Hello"
greet input name String borrowed
greet input resultRegion Region borrowed
greet output String
greet outputOwner resultRegion
greet raises none
greet effect none
greet uses none
greet memory heap true
greet memory stack 256
greet memory max 4096
greet async false
greet let prefix immutable String "Hello, "
greet at entry do joinText
greet at entry return ok greeting

joinText is call
joinText in greet
joinText invokes string.concat
joinText arg left String prefix lend
joinText arg right String name lend
joinText arg region Region resultRegion lend
joinText out greeting String
joinText ownedBy resultRegion
joinText borrows none
joinText catch none
```

`greet` allocates nothing of its own: the result lives in the region its caller
passed in, and the caller's region declaration says when that memory is freed.

#### Corpus work this implies

- Replace the 29 identical `defer_*` examples with examples that each exercise
  one rule above against a real resource or region.
- Add an accepted example and a rejected example for every row in the probe
  table.
- Port the standard library's string, JSON, and SQLite text results to take a
  region, and remove the process-lifetime allocation model.

### LR-21 Comments and extra context

Status: decided (2026-11-13; item 4 overturned by the owner the same day:
comments stay)

#### How it works at `b6aa5c7`

Context can be written four ways:

1. **Plain comments.** `#` at column 1, or trailing after a row. Free text,
   ignored by the checker, kept by `fmt`, included in `slice` output.
2. **Typed comments.** `# <tag>: text` with 17 fixed tags (`rationale`,
   `warning`, `agent`, `memory`, `concurrency`, `timing`, `failure`, `security`,
   `dependency`, `observability`, `test`, `todo`, `purpose`, `invariant`,
   `note`, `risk`, `example`). `check --json` returns them with line numbers.
3. **Metadata rows** on any entity: `purpose`, `invariant`, `note`,
   `rationale`, `risk`, `example`, `tag`, `deprecated`, `owner`. Labels take
   them through `<op> label <label> <predicate> "<text>"`.
4. **Reason strings inside rows**: `discards "<reason>"`, `because "<reason>"`.

Probe (`comments.sem`, a hello world with one comment of each kind):

- A plain comment written between two rows of `main` is moved by `fmt` to above
  `main is operation`. It no longer sits next to the row it explained.
- A comment after an entity's last row is attached to the next entity.
- `# madeUpTag: ...` is accepted silently as a plain comment, so a misspelled
  tag is lost without a diagnostic.
- `slice` carries all comments and metadata rows for the entity. (An earlier
  note in this discussion said comments might not travel with slices; that was
  wrong.)

Corpus:

- Typed comments: 0 uses in `examples/` and in `apps/taskforge-web`.
- Metadata rows other than `purpose`/`invariant`: `rationale` 19 and `risk` 10
  across the apps; `note`, `example`, `tag`, `deprecated`, and `owner` 0.
- 233 examples open with `# Expected output: ...`. The example runner does not
  read it, so the stated output is never compared with the real output.

Problems under P-1 and P-2:

- Five tags exist both as rows and as typed comments: two spellings of one fact.
- A comment's subject is inferred from where it sits, and `fmt` changes where it
  sits.
- Comments get none of the LR-06 protections (staleness flag, filler check).
- The `agent` tag is a channel for instructions to whichever model reads the
  file next. Text in source should describe the code, not direct the reader.

#### Decision

Two mechanisms with different jobs:

- **Comments are free space.** Authors, which here means agents, fill them as
  they see fit. They carry no machine meaning and are never checked.
- **Context rows are structured.** They have a subject, a closed vocabulary, and
  the LR-06 protections. Anything a tool must act on is a row.

1. **`#` comments stay**, both full-line and trailing, with no restriction on
   content. (The first version of this decision removed them. The owner
   overturned that: comments exist for agents to use freely.)
2. **A comment has no tags.** The typed-comment grammar is removed, so there is
   one spelling for structured context (a row) and a misspelled tag can no
   longer be silently lost. `# todo: ...` is still a perfectly good comment; it
   is just not parsed.
3. **A comment stays where it was written.** A full-line comment belongs to the
   next row; a trailing comment belongs to its own row; comments after the last
   row belong to the file. `fmt` never moves a comment relative to its row, and
   when canonical ordering moves a row, its comments move with it. This fixes
   the hoisting found in the probe.
4. **Comments travel.** `slice` and other views that show a row show its
   comments.
5. **Comments are never evidence.** No check passes or fails because of a
   comment, and tools present them as author notes, not as facts about the
   code.
6. **Closed set of context rows:**

   | Row | Meaning |
   | --- | --- |
   | `<e> purpose "<text>"` | Why it exists. Unchecked intent (LR-06). |
   | `<e> invariant <id> "<text>"` | A claim backed by a test (LR-06). |
   | `<e> rationale "<text>"` | Why it is built this way, so a later author does not "fix" a deliberate choice. |
   | `<e> risk <category> "<text>"` | A known hazard. Category is one of `security`, `failure`, `timing`, `concurrency`, `memory`, `data`. |
   | `<e> note "<text>"` | Context that should survive and be staleness-checked but fits none of the above. |
   | `<e> todo "<text>"` | Work still owed. Listed by tooling; a release gate may reject any. |
   | `<e> deprecated "<text>"` | What to use instead. |

   `example`, `tag`, and `owner` are removed (unused, and `owner` collides with
   ownership vocabulary).
7. **Subjects.** A context row attaches to an entity, or to a block through
   `<op> label <label> <predicate> ...`.
8. **LR-06 rules apply to context rows, not to comments**: the staleness flag
   when the entity's structural rows change, and the filler check.
9. **Reasons stay where a row waives a check.** `discards "<reason>"` and
   `because "<reason>"` keep their inline strings and remain required.

Rule of thumb for authors: if the next reader must not miss it, or a tool should
track it, write a row. Otherwise write a comment.

#### Worked example

```
main is operation
main purpose "Print a greeting and exit cleanly"
main invariant exitsZero "Exits with code zero"
main rationale "The greeting is a fixed literal so the demo has no input"
main risk security "Must never print user-supplied text without escaping"
main todo "Replace the fixed greeting with a configured one"
main label failed purpose "Shared exit for any write failure"
# Tried building the greeting with string.concat first; a literal is simpler.
main at entry do greetCall   # the only step that touches stdout
```

### LR-22 Loops, retries, and recursion

Status: decided (2026-11-13, accepted by owner)

#### How it works at `b6aa5c7`

- **A loop is a label and a backward `goto`.** There is no loop construct.
  60 of the examples contain one.
- **`maxIterations <n>`** is an operation-level row. Its only effect is to
  silence SS0951, which fires when a loop's exit test reads untrusted input.
  Probes on the sum-to-five example:
  - `main maxIterations 2` on a loop that runs five times passes `check --strict`
    and the program prints 15. The bound is not enforced at compile time or at
    run time.
  - `main maxIterations banana` passes.
  - No example or app has a `maxIterations` row.
- **Stuck loops.** SS0950 catches a loop with no exit path at all. A loop whose
  counter never advances (the increment deleted) is not reported.
- **Retries are a hidden loop.** `useRetry <n>` on a call re-invokes it up to
  `n` times, with `retryBackoffMs` between attempts. The repetition appears in
  no step row.
- **Recursion** traps at a compiler constant (`EAV_RECURSION_LIMIT`). The limit
  is not stated in source.

#### Decision

Builds on LR-16 (explicit control-flow graph) and LR-18 rule 7 (bounds attach to
the block).

1. **A loop is a block that some `goto` or `branch` jumps back to.** No loop
   keyword. Leaving early and skipping ahead are ordinary jumps to named blocks.
2. **Every loop block states its bound**, and only loop blocks may:
   `<op> label <label> maxIterations <bound>`. `<bound>` is an integer literal
   or the name of an immutable `Int64` value, so a loop over run-time data can
   be bounded by a stated cap. A missing row on a loop block is an error; the
   row on a block nothing jumps back to is an error.
3. **The bound is enforced.** The compiler counts entries to the block per run
   of the operation and traps with a structured panic naming the operation and
   label when the count passes the bound. When the trip count is a compile-time
   constant, a bound smaller than it is a check error.
4. **Unbounded loops are stated.** `<op> label <label> maxIterations unbounded`
   requires `<op> label <label> because "<reason>"`. This is for accept loops
   and event loops.
5. **No hidden repetition.** `useRetry` and `retryBackoffMs` are removed. A
   retry is written as a loop block with a bound, an attempt counter, and an
   explicit delay call.
6. **Recursion states its depth.** An operation that can reach itself through
   calls states `<op> maxRecursion <n>`. The compiler enforces it with the
   existing depth guard, using the stated number in place of the global
   constant. The row is an error on an operation that cannot recurse.
7. **Progress is not proven.** The compiler does not try to prove a loop
   advances; the enforced bound is the safety net. SS0950 stays for the case it
   can decide (no exit path).
8. **Iterating a collection** uses the same loop block, driven by calls that
   fetch the next item. Its design belongs to LR-10.

#### Worked example

A retry, written out (in the form amended by Part 3):

```
fetch label begin loopKind none
fetch label begin within none
fetch label attempt loopKind doWhile
fetch label attempt within none
fetch label attempt maxIterations 2
fetch label countAttempt loopKind none
fetch label countAttempt within attempt
fetch label backoff loopKind none
fetch label backoff within attempt
fetch label succeeded loopKind none
fetch label succeeded within none
fetch label gaveUp loopKind none
fetch label gaveUp within none
fetch let maxAttempts immutable Int64 3
fetch let one immutable Int64 1
fetch let attemptsMade mutable Int64 0
fetch at begin goto attempt
fetch at attempt do requestPage
fetch at attempt branch ifError requestPage goto countAttempt else goto succeeded
fetch at countAttempt do addAttempt
fetch at countAttempt set attemptsMade nextAttempts
fetch at countAttempt do attemptsLeftCheck
fetch at countAttempt branch if attemptsLeft goto backoff else goto gaveUp
fetch at backoff do waitBeforeRetry
fetch at backoff goto attempt
fetch at succeeded return ok pageText
fetch at gaveUp return ok emptyText
```

Three attempts means returning to `attempt` at most twice, so the bound is 2.

### LR-23 Loop kinds as declared, checked shapes

Status: decided (2026-11-13, accepted by owner). Extends LR-22.

- **Problem**: Under LR-22 a loop is "a block something jumps back to". The
  bound is stated, but the loop itself is still inferred from the shape of the
  graph: which blocks belong to it, where it may be entered, and what kind of
  loop the author meant. P-2 says nothing is implied. An inferred loop also
  gives the checker nothing to hold the code to, which is why a counter that
  never advances goes unreported.
- **Decision**: a loop is declared on its header block with a kind from a
  closed set, every block in it states its membership, and the compiler checks
  the blocks against the shape that kind requires.

#### Rows

```
<op> label <header> loop <kind>            # counted | while | doWhile | forEach | forever
<op> label <header> maxIterations <bound>  # LR-22; `unbounded` only with kind forever
<op> label <header> counter <name>         # kind counted only
<op> label <block> within <header>         # every other block of the loop
```

A nested loop's header states `within <outerHeader>`.

#### Rules for every kind

1. **Single entry.** A block outside a loop may jump only to the loop's header.
   Jumping into the middle of a loop is an error.
2. **Stated membership.** A block that states `within H` may jump to another
   block within `H`, to `H` itself (next iteration), or to a block outside `H`
   (leaving the loop). The compiler rejects any jump the declarations do not
   allow, and any block on a cycle that declares no loop.
3. **Leaving early and skipping ahead are jumps.** Leaving several nested loops
   at once is a jump to a block outside all of them. No `break` or `continue`
   keywords.
4. **Bound enforced at run time** (LR-22), counted per entry to the header.

#### Kinds

| Kind | What it is | Shape the compiler checks | Termination |
| --- | --- | --- | --- |
| `counted` | Runs a number of times fixed before it starts | Header tests the counter against an immutable limit and branches in or out. Exactly one `set` of the counter in the loop, from the counter plus or minus an immutable non-zero step, in the direction of the limit. | Proven at check time. A counter that does not advance is an error. |
| `while` | Tests a condition first; body may run zero times | Header ends in a two-target branch: one target within the loop, one outside. | Run-time bound. |
| `doWhile` | Runs the body, then tests; body runs at least once | Header is the first body block. The branch that returns to the header or leaves is in a later block. | Run-time bound. |
| `forEach` | Visits each item of a collection once | Defined with collections (LR-10). The collection may not be changed inside the loop. | Bounded by the collection's length. |
| `forever` | A service loop that is meant not to end | `maxIterations unbounded` and a `because` row. | None, by declaration. |

#### How familiar loops are written

| Loop | Written as |
| --- | --- |
| `for i in 1..n` | `counted` |
| `while condition` | `while` |
| `do ... while condition` | `doWhile` |
| `for item in list` | `forEach` (after LR-10) |
| `while true` server or event loop | `forever` |
| Retry up to n times | `counted`, leaving early on success |
| Poll until ready, with a delay | `while`, with a bound |
| Search with early exit | any kind, with a jump out to a "found" block |
| Loop with the test in the middle | `while` or `doWhile`, with the exit branch in a middle block |
| Nested loops | inner header `within` the outer header |
| State machine | `while` whose header branches on a state enum with `ifVariant` |
| Recursion | not a loop; `maxRecursion` (LR-22) |

#### Not representable, on purpose

- A loop with no stated bound that is not declared `forever`.
- Jumping into the middle of a loop, or a cycle with two entry points.
- A jump to a computed target.
- Loops inside expressions (comprehensions): there are no expressions.
- Generators or coroutines that pause mid-loop: use tasks (LR-17).
- Parallel loops: use workers (LR-17).

#### Worked example

The sum-to-five loop (in the form amended by Part 3):

```
main label begin loopKind none
main label begin within none
main label sumLoop loopKind counted
main label sumLoop within none
main label sumLoop maxIterations 5
main label sumLoop counter nextNumber
main label addStep loopKind none
main label addStep within sumLoop
main at begin goto sumLoop
main at sumLoop do pastLimitCheck
main at sumLoop branch if pastLimit goto finish else goto addStep
main at addStep do addToTotal
main at addStep set total nextTotal
main at addStep do addOne
main at addStep set nextNumber afterNextNumber
main at addStep goto sumLoop
```

Deleting `main at addStep set nextNumber afterNextNumber` is now a check error: a
`counted` loop must advance its counter.

## Part 2: completing the language (LR-24 to LR-41)

Status of every item in this part: decided 2026-11-13 by delegation. The owner
asked for further refinement notes in line with the earlier decisions, with one
target: enough language to write an HTTP server and SemanticScript's own
compiler. Each item is open to reversal like any other.

Two worked examples exercise this part end to end:

- `docs/refined-examples/server/`: listen, accept forever, one task per
  connection, a static route table, per-request region.
- `docs/refined-examples/selfhost/`: read a word token from source text and
  classify it against a keyword table, then tokenize into a list.

Both pass the refined checker (Part 4). Neither runs yet.

### What the two targets need

| Need | HTTP server | Compiler | Item |
| --- | --- | --- | --- |
| Lists and maps of any type | headers, routes | tokens, rows, symbol tables | LR-24, LR-25 |
| Iterating a collection | match a route | every pass | LR-25 |
| Static lookup data | route table | keywords, predicate shapes, diagnostics | LR-26 |
| Byte and text access | parse a request | lex source | LR-27 |
| Records, variants, optional values | request, response | tokens, entities, AST | LR-28 |
| A value set on several paths | the response | most results | LR-29 |
| Errors with data | parse failures | diagnostics | LR-30 |
| Mutating through a loan | append to a list | append to a list | LR-31 |
| Several files | handlers per file | one module per pass | LR-32 |
| Waiting on I/O, many tasks | accept, read, write | none | LR-33 |
| Arguments, streams, exit code | port from arguments | file names, exit status | LR-34 |
| Files and sockets | sockets | read source, write output | LR-35 |
| HTTP itself | parse and serialize | none | LR-36 |
| Passing an operation as a value | handlers | visitors, comparators | LR-37 |
| Exact integer behavior | lengths, status codes | offsets, widths, hashing | LR-38 |
| Tests tied to invariants | handlers | every rule and diagnostic | LR-39 |
| A standard library to stand on | net, http, time | string, byte, fs, process | LR-40 |

### LR-10 Collections, loops, and generics (resolved)

Loops were settled in LR-16, LR-22, and LR-23. Generics are LR-24 and
collections are LR-25. This item is closed.

### LR-24 Generics by named instantiation

- **Now**: `typeParam T` on a record, enum, or operation, and
  `<Name> instantiates <Generic> <Type>` to create a concrete type (three
  examples use it). The standard list is not generic: `list.*` works on a
  `ListHandle` of `Int64` only.
- **Decision**:
  1. Keep `typeParam` and `instantiates`. There is no inference and no type
     application inside a row: a generic is used only through a named
     instantiation.
     ```
     HeaderList is record
     HeaderList instantiates List Header
     ```
  2. An instantiation is an ordinary named type with derived call targets, the
     same way `<Record>.new` is derived today: `HeaderList.new`,
     `HeaderList.append`, `HeaderList.get`. One instantiation per distinct type
     argument list per module; a second with the same arguments is an error.
  3. A generic operation is likewise called only through a named instantiation:
     `sortTokens is operation` / `sortTokens instantiates sort Token`.
  4. A type parameter may be constrained by one row,
     `<Generic> typeParam T plain | any`. `plain` admits only values with no
     owner (LR-20), which is what lets a container copy its elements.

### LR-25 Collections and iteration

- **Now**: `list.*` (5 targets, `Int64` only) and `map.*` (5 targets), both
  with a manual `release`. No iteration support; examples index by hand.
- **Decision**:
  1. The standard library defines generic `List T`, `Map K V`, and `Set T`.
     They are region-owned (LR-20): `new` takes a region, and there is no
     `release` target.
  2. Reads that can miss are fallible: `<List>.get` raises `IndexOutOfRange`,
     `<Map>.get` raises `KeyMissing`. There is no unchecked access.
  3. Mutating targets (`append`, `put`, `remove`, `clear`) take the collection
     as `lendMutable` (LR-31).
  4. **`forEach`** (LR-23) is driven by one guard:
     ```
     <op> label <header> loop forEach
     <op> label <header> over <collection>
     <op> label <header> maxIterations <bound>
     <op> at <header> branch ifNext <collection> bind <item> goto <body> else goto <done>
     ```
     The compiler keeps the position. `<item>` is a copy when the element type
     is plain and a borrowed view otherwise. Inside the loop the collection may
     not be passed as `lendMutable` or `give`. The `ifNext` row must be the only
     row of the header block.
  5. **Typed positions.** An index into a particular list is its own type:
     ```
     NodeId is alias
     NodeId for Int64
     NodeId indexes NodeList
     ```
     `<List>.get` on `NodeList` accepts only a `NodeId`. This is how trees and
     graphs are built: nodes live in a list and refer to each other by id. There
     are no pointer types in application source.

### LR-26 Static data tables

- **Now**: no way to write constant compound data. Lookup tables are built by
  calls at start-up, and the compiler's own tables live in Python.
- **Decision**: a `table` entity holds constant records, one fact per row.
  ```
  keywords is table
  keywords of Keyword
  keywords cell isWord text "is"
  keywords cell isWord kind keywordIs
  keywords cell atWord text "at"
  keywords cell atWord kind keywordAt
  ```
  1. `of` names a record type whose fields are plain values, static strings, or
     operation references.
  2. `cell <rowId> <field> <value>`: every row id must state every field
     exactly once. Row order is the order row ids first appear.
  3. A table is owned by the built-in region `static` and is read-only. It
     supports `forEach`, `<table>.length`, and `<table>.get` by row id.
  4. This is also the form for the predicate shape table and the diagnostic
     registry once the compiler is self-hosted.

### LR-27 Text and bytes

- **Now**: `string.*` has 9 targets: concat, compare, find, byte length. There
  is no way to read one byte, take a slice, or parse a number, so a lexer or a
  request parser cannot be written.
- **Decision**:
  1. Three types. `String` is immutable, valid UTF-8 text. `Bytes` is immutable
     raw bytes. `ByteBuffer` is a growable, mutable buffer. All are region-owned,
     except string literals and table cells, which belong to `static`.
  2. No implicit conversion. `string.fromBytes` validates and is fallible;
     `string.toBytes` is a view.
  3. Positions are byte offsets (`Int64`). Required targets:
     `string.byteLength`, `string.byteAt` (fallible), `string.slice` (fallible,
     returns a view that `borrows` the source), `string.equals`,
     `string.startsWith`, `string.find` (returns an optional offset),
     `string.concat` (takes a region), `string.toInt64` (fallible),
     `string.fromInt64` (takes a region).
  4. Byte classification lives in `standard.byte`: `byte.isLetter`,
     `byte.isDigit`, `byte.isLetterOrDigit`, `byte.isSpace`, `byte.equals`.
  5. Text is assembled with a `ByteBuffer`: `buffer.new` (region),
     `buffer.appendString`, `buffer.appendByte`, `buffer.appendInt64` (all
     `lendMutable`), then `buffer.toString` (fallible) or `buffer.toBytes`.
  6. Unicode scalar values are `Rune` (`UInt32`) with `string.decodeRuneAt`
     (fallible). Nothing in the core depends on it.

### LR-28 Records, variants, and optional values

- **Now**: `<Record>.new`, `<Record>.<field>`, `<Enum>.<variant>`, and
  `branch ifVariant ... bind` exist. A record cannot be changed after it is
  built, and there is no standard optional type.
- **Decision**:
  1. Keep the derived targets. Add `<Record>.with<Field>` (record and new value
     in, new record out) and `<Record>.equals` / `<Enum>.equals`.
  2. Records and enums are immutable values. A value that changes is a mutable
     `let` that is `set` to a new record.
  3. **Class follows contents** (LR-20). A record or variant is plain if every
     field is plain. If any field is region-owned, the whole value is owned by
     that same region, and `<Record>.new` takes the region as an argument. A
     record may not hold an operation-owned resource.
  4. A field read of a region-owned field returns a view: `borrows <record>`.
  5. The standard library defines `Option T` with variants `some` (payload `T`)
     and `none`. "Maybe a value" is always an instantiated `Option`, never `nil`.
     The `nil` literal is removed.
  6. `ifVariant` chains must cover every variant (LR-16.5).

### LR-29 Values set on more than one path

- **Now**: a name bound by one call cannot be bound by another, so a value that
  comes from different calls on different paths has no spelling. Authors
  duplicate everything downstream.
- **Decision**: declare the merge explicitly.
  ```
  handleConnection let response mutable HttpResponse unset
  handleConnection at dispatch set response handlerResponse
  handleConnection at badRequest set response badRequestResponse
  ```
  `unset` is a declared absence of an initial value, legal only on a mutable
  `let`. Definite assignment (LR-04) rejects any read that some path reaches
  without a `set`. If the type is region-owned, every assigned value must be
  owned by the same region.

### LR-30 Errors and returns

- **Now**: `error` and `errorCase` entities, `raises` rows, `out Result`,
  and positional returns such as `return nil writeError`.
- **Decision**:
  1. Errors are enums (as §34 already plans). A variant may carry a payload,
     including the lower-level error that caused it.
  2. Every operation states `<op> raises <ErrorEnum> | none`. Exactly one row.
  3. Every return says which it is:
     `<op> at <label> return ok <value> | none` or
     `<op> at <label> return error <value>`. `return error` is legal only when
     `raises` names that enum.
  4. A call to an operation that `raises` must state `catch <name> <ErrorEnum>`
     and is followed at once by `branch ifError` (LR-16.4).
  5. There is no propagation shorthand. To pass a failure up, the failure block
     builds this operation's own error variant and returns it. If the types are
     the same it returns the caught value.
  6. Deliberately ignoring a failure is written as a branch whose two targets
     are the same block. The row stays visible; a comment or `rationale` row
     says why.
  7. Traps (overflow, bound exceeded, out of memory) are not errors. They end
     the task with a structured panic and cannot be caught.

### LR-31 Passing modes and call skeleton, completed

Amends LR-20 after writing the worked examples.

1. **Four modes.** A loan is read-only or exclusive:

   | Operation `input` | Call `arg` | Meaning |
   | --- | --- | --- |
   | `value` | `copy` | plain value, copied |
   | `borrowed` | `lend` | read-only loan |
   | `borrowedMutable` | `lendMutable` | exclusive loan; the callee may change it |
   | `owned` | `give` | ownership moves to the callee |

   While a value is lent with `lendMutable` it may not appear in another
   argument of the same call. Lending a `Region` so the callee can allocate in
   it is `lend`.
2. **Call and task skeleton**, in order: `in`, `invokes`, `arg` rows, `out`,
   `ownedBy`, `borrows`, `catch`. `out none` when there is no result;
   `borrows none` when the result is not a view.
3. **`cleanedBy`** is required exactly when `ownedBy` names the operation. Its
   value is a cleanup entity, or `none` when every path gives or returns the
   value (the accepted connection in the server example).
4. **Operation skeleton**, in order: context rows, `input` rows (or
   `input none`), `output`, `outputOwner`, `raises`, `effect` rows (or
   `effect none`), `uses` rows (or `uses none`), `memory heap`, `memory stack`,
   `memory max`, `async`, then labels, `let` rows, and steps.
5. **`outputOwner`** is `none` (plain result), the name of a `Region` input, or
   `caller` (an operation-owned resource handed to the caller).
6. **`static`** is a built-in region that lives for the whole run. String
   literals and tables are owned by it. Nothing can be allocated in it at run
   time.

### LR-32 Modules and imports

- **Now**: `imports`, plus five selective predicates (`importOperation`,
  `importType`, `importError`, `importCapability`, `importConstant`). Standard
  targets such as `string.concat` need no import at all.
- **Decision**:
  1. One file is one module. `<module> path <dotted.path>` must match the file's
     location.
  2. One way to import: `<module> imports <dotted.path>`, one row per module
     used, standard library included. The five selective predicates are removed.
  3. An imported name is always written with its module's last path segment:
     `string.concat`, `lexer.scanWord`. Two imports with the same last segment
     are an error; there are no aliases. A name with no prefix is local to the
     module.
  4. `exports` lists every name visible outside, one row each. Everything else
     is private.
  5. Import cycles are an error.
  6. The `project` entity lives only in `build.sem`.

### LR-33 Waiting, deadlines, and many tasks

Builds on LR-17.

1. **A call that can wait is a task.** Any target that may suspend (socket and
   file I/O, timers, channel receive) is `async true` and can only be invoked
   through a `task` entity with `start` and `join`. `join` is the visible
   suspension point. `do` never suspends.
2. **Every waiting target takes a `Deadline`.** `Deadline.after` (milliseconds)
   or `Deadline.never`. There are no default timeouts. A missed deadline is an
   ordinary error variant.
3. **Cancellation is an error path.** `cancel <task>` makes the task's pending
   wait fail with a `cancelled` variant, which the task handles like any other
   failure and then releases what it owns.
4. **Task groups** own a changing number of tasks:
   ```
   connections is taskGroup
   connections in main
   connections limit 256
   connections atReturn joinAll        # joinAll | cancelAll

   main at startHandler start handleTask into connections
   main at stopped join connections
   ```
   `start ... into` at the limit waits for a slot. A group is owned by one
   operation and is joined or cancelled on every path to its `return`.
5. **Operations that `join` anything are `async true`.** The entry operation
   may be.
6. **Channels** (`Channel T`, an instantiated generic) carry values between
   tasks and between workers. `send` uses `give` for owned values.

### LR-34 The edges of a program

1. **Entry.** `main input none`, `main output ExitCode`. Everything else comes
   through capability-gated calls.
2. **Arguments and environment.** `process.argumentCount`, `process.argument`
   (fallible, by index), `environment.get` (fallible).
3. **Standard streams.** `console.readLine` (fallible, takes a region and a
   maximum length), `console.write`, `console.writeLine`, `console.writeError`.
4. **Other programs.** `process.run` (program, argument list, deadline) under a
   `process.spawn` capability. A self-hosted compiler writes LLVM IR as text and
   runs the system linker this way; no foreign-function binding is needed.
5. **Capabilities carry a scope.** Every capability has exactly one `scope`
   row: a quoted prefix (a directory, an address and port, a program name) or
   `none` when the resource kind has no scope. A call outside the stated scope
   fails with a permission error at run time, and a literal argument outside
   the scope is a check error.
6. **Time.** `clock.now` (wall time) and `clock.monotonic` under a clock
   capability. There is no ambient time.

### LR-35 Files and network resources

- **Now**: `fs.*` can only read (6 targets). `net.*` is client-only (6
  targets); serving is done by the `webServer` entity and a C runtime.
- **Decision**: both are operation-owned resources (LR-20).
  1. Files: `fs.openRead`, `fs.openWrite`, `fs.create`, `fs.read` (region,
     maximum bytes, deadline), `fs.write`, `fs.close`, `fs.exists`, `fs.remove`,
     `fs.list`, and the convenience pair `fs.readAll` / `fs.writeAll` with a
     stated maximum size.
  2. Sockets: `net.listen`, `net.accept`, `net.connect`, `net.read`,
     `net.write`, `net.close`, `net.closeListener`. Every read states a maximum
     byte count.
  3. Handles are `owned` by exactly one operation, lent to tasks that read and
     write, and given to the task that will close them.

### LR-36 HTTP is a library

- **Now**: `webServer` is an entity kind with `route`, `host`, `port`, and
  other keywords; `htmlTemplate` and SQL/JSON/HTML "islands" make indentation
  meaningful inside a `body` row.
- **Decision** (carries out §34.3):
  1. Remove the `webServer` entity, the `webServer` target, and its keywords. A
     server is a console program that listens (see the worked example).
  2. `standard.http` is written in SemanticScript: `HttpRequest`,
     `HttpResponse`, `HttpMethod`, `http.parseRequest`, `http.response`,
     `http.serializeResponse`, `http.header`. Parsing limits (header count,
     line length, body size) are arguments, not hidden constants.
  3. Routing is a `table` of method, path, and handler (LR-26, LR-37).
  4. Remove islands and `htmlTemplate`. Indentation is never meaningful. Long
     text is a string literal or an embedded file (`literalSource` with its
     digest); HTML and SQL are built by library calls that escape by
     construction.

### LR-37 Operations as values

- **Now**: `operationType` declares a signature; a named operation can be
  passed and invoked indirectly. No closures.
- **Decision**: keep it, with the full skeleton.
  1. An `operationType` states `input` rows with modes, `output`,
     `outputOwner`, and `raises`. An operation matches only if every one of
     those rows is identical.
  2. Operation references are plain values. They may be stored in a `let`, a
     record field, or a table cell.
  3. The effects of an indirect call are those the `operationType` declares
     with `effect` rows (or `effect none`). An operation with more effects than
     the type allows cannot be used as a value of that type.
  4. Still no closures. State is passed as an argument.

### LR-38 Numbers

1. Fixed-width integers and floats only. No implicit conversion or promotion,
   including between signed and unsigned (LR-12).
2. Arithmetic targets name their type and behavior:
   `math.addInt64` traps on overflow; `math.wrappingAddInt64` and
   `math.saturatingAddInt64` are separate targets. Division and remainder trap
   on zero.
3. Comparison is by call: `compare.equalInt64`, `compare.lessThanInt64`,
   `compare.greaterOrEqualInt64`, and so on for each type. The comparator
   keywords inside `branch` are already removed (LR-15).
4. Bit operations are calls in `standard.bits`.
5. `Byte` is `UInt8`. A literal takes the type its position states and is
   range-checked at compile time.

### LR-39 Tests

Finishes LR-06.

1. A `test` is an entity kind with the operation skeleton, no inputs, and no
   output. It lives in a `<name>.test.sem` file beside the module it tests.
   ```
   healthIsOkTest is test
   healthIsOkTest verifies handleHealth healthIsOk
   healthIsOkTest purpose "A health request gets status 200"
   ```
2. `verifies <operation> <invariantId>` may repeat. Every `invariant` must be
   named by at least one test, and every `verifies` must name a real invariant.
3. Assertions are calls in `standard.test`; a failed assertion fails the test
   and reports the operation, the invariant id, and the row.
4. A test declares its effects and capabilities like any operation.
5. Compiler tests for rejected programs are fixtures with one stated
   expectation: `<fixture> expectsDiagnostic <code>`.

### LR-40 The standard library contract

1. Every standard target has a signature stating its inputs with modes, output
   and owner, errors, effects, whether it can wait, and whether it allocates
   (it takes a `Region` if so).
2. The library is written in SemanticScript wherever possible. Raw bindings to
   the C runtime are confined to a small core (`memory`, `byte`, `fs`, `net`,
   `process`, `clock`) and are the only place `runtimeBinding` is legal.
3. Modules the two targets need: `string`, `byte`, `bits`, `math`, `compare`,
   `list`, `map`, `set`, `option`, `buffer`, `fs`, `net`, `http`, `time`,
   `clock`, `process`, `environment`, `console`, `test`.
4. Each module ships with an accepted example and a test for every target.

### LR-41 What is still missing

Known gaps after this part, in the order they would block real work:

1. **Floating-point formatting and parsing** beyond `convert`. Needed for JSON.
2. **JSON** as a library on top of LR-27 and LR-28.
3. **TLS.** The server example is plain HTTP.
4. **Sorting and hashing** as generic operations (LR-24 covers the mechanism).
5. **Worker pools** for CPU-bound work (LR-17 layer 3 names them; no row shapes
   yet).
6. **Incremental and separate compilation** rules for modules.
7. **A formal grammar** generated from the shape table (plan step 1).

## Part 3: amendments after adversarial review (LR-42)

Status: decided 2026-11-13 by delegation. Not reviewed by the owner.

An independent reviewer was given the notes, the worked examples, and the
checker, with instructions to break the design against its own goal: a very low
perplexity, fully explicit, agent-first language. It reported 17 findings. Each
was checked against the files before being acted on; all held.

**Where this part conflicts with Part 1 or Part 2, this part wins.** The worked
examples follow it, and the refined checker (Part 4) enforces it.

### The cold-write test

The reviewer wrote a new program (count the words on each input line) using
only this file, then ran the checker.

- **First attempt: 4 checker errors, one cause.** It wrote `arg none` on calls
  with no arguments, as LR-18.1 says. The examples and the checker omitted the
  row. The rule was right and the examples were wrong (A1).
- **Twelve guesses the checker could not see**, each now answered below: effect
  vocabulary (A8), whether console reads wait (A25), error and slot names
  (A26), whether `ExitCode` is built in (A26), memory numbers (A18), literals in
  arguments (A23), how end of input is signalled (A6, A25), which loop kind
  reads until end of input (A25), row order outside operations (A22), tests
  (A17), and allocating in a loop (A24).

This is the first measurement behind plan step 12. The target is zero errors
and zero guesses on a first attempt.

### Amendments

| # | Finding | Rule now |
| --- | --- | --- |
| A1 | Calls with no arguments omitted their `arg` rows: an empty set by absence | Every call and task has at least one `arg` row; with no arguments it is `arg none`. |
| A2 | `maxIterations` counted entries to the header, so five passes needed `6`, and the lexer example trapped on a word that ran to the end of the source | `maxIterations` counts returns to the header from inside the loop. Five passes is `5`. |
| A3 | Imported types and enum variants were written bare, against LR-32.3; a module had two names | An imported type is `module.Type` (`net.NetError`, `http.HttpRequest`). A variant is always `Enum.variant`, in every position. A module entity is named after the last segment of its `path`. Built-in, unprefixed types: the fixed-width numbers, `Bool`, `Byte`, `String`, `Bytes`, `Region`, `ExitCode`. |
| A4 | `ifNext ... bind candidate` gave no type; which names an `ifError` branch puts in scope was unstated | `branch ifNext <collection> bind <name> <Type> ...`. After `branch ifError <call>`, the call's `catch` name is in scope only on the error arm and its `out` name only on the `else` arm. A task's `out` and `catch` names are bound at `join`. A `forEach` starts from the first element each time its header is entered from outside the loop. |
| A5 | Value keywords shared positions with user names; `nil` was reserved and removed; `none` was a literal and an `Option` variant | Reserved: `true`, `false`, `none`, `caller`, `unset`, `unbounded`, `static`, `begin`. `nil` is not a word. `Option` has variants `present` and `absent`. |
| A6 | `ifVariant` had no stated shape and its "declared default" was undefined | Variant inspection is one construct that is exhaustive by construction. A block ends in `<op> at <L> match <value> <EnumType>` followed by one `<op> at <L> case <Enum.variant> bind <name\|none> <Type\|none> goto <label>` row per variant. Every variant appears exactly once. `ifVariant` is removed. |
| A7 | Payloadless variants omitted the payload | `<Enum> variant <name> <PayloadType\|none>`. |
| A8 | Effect and `grants` words were never defined | `effect <verb> <module>.<resource>` with verbs `read`, `write`, `readWrite`, `listen`, `connect`, `spawn`. The resources are published by each library module's signature; there is no other source of them. |
| A9 | The cleanup skeleton was undefined; `logAndSuppress` logged with no effect; the cleanup's fallible call had no error path | Cleanup rows, in order: `in`, `call`, `cleans`, `onFailure suppress\|trap`, `because`. The worker call is run by the cleanup, not by `do`, so the `ifError` rule does not apply to it; `onFailure` is its error path. Nothing is logged implicitly. |
| A10 | Slot names of derived targets were unstated | `<Record>.new`: one slot per field, named by the field. `<Record>.<field>`: slot `record`. `<Record>.with`: slot `record` plus one slot named by the field to change. `<Enum>.<variant>`: slot `payload`, or `arg none`. `equals`: `left`, `right`. |
| A11 | `HttpHandler` stated no effects or `async`; an indirect call looked like a direct one | An `operationType` states `effect` rows (or `effect none`) and `async`. A call through a reference uses `invokesReference <binding>`, never `invokes`. A reference whose type is `async true` is invoked through a task. |
| A12 | `start ... into` could wait; `atReturn joinAll` duplicated an explicit `join` and one path skipped it | A task group has no `atReturn` row. Every path to a `return` states `join <group>` or `cancel <group>`. Waiting for room is its own step, `awaitSlot <group>`; `start ... into` a full group traps. |
| A13 | Several skeleton rows existed only conditionally, so "not a loop" and "not recursive" were stated by absence | `cleanedBy` is on every call (`none` when it does not apply), after `ownedBy`. Every operation states `maxRecursion <n>\|none`. Every block states `label <L> loopKind <kind\|none>` and `label <L> within <header\|none>`. The predicate is `loopKind`, which also ends `label loop loop counted`. The first block is `begin`, since `entry` is a project predicate. |
| A14 | "Exactly one `set`" did not prove a `counted` loop advances; the bound was only checked one way | Exactly one `set` of the counter on every path from the header back to the header. When the trip count is a compile-time constant, `maxIterations` must equal it. |
| A15 | The LR-22 retry example declared no loop; a retry cannot have the `counted` header shape | A retry is a `doWhile` with a bound. The example is corrected. |
| A16 | Ignoring a failure had two rules, one of which relied on a comment | A same-target `branch ifError` requires a `rationale` row on the call. `discards "<reason>"` is only for an unused result. |
| A17 | Tests needed their own invariants (a regress); private operations were untestable; mandatory invariants on helpers invite untrue prose; the filler check read English | A test file is part of the module beside it. A test states `verifies` and no `invariant`. A non-exported operation may state `invariant none`. The filler check is mechanical: empty, under ten characters, or equal to the entity's name ignoring case and spaces. |
| A18 | `memory stack` and `memory max` were required numbers with no meaning, so authors invent them | Both rows are removed. Memory is stated by `memory heap true\|false` and by each region's `capacity`. **This reverses part of LR-20 rule 10, which the owner accepted.** |
| A19 | The checker called a jump "backward" by text order; the notes never ordered blocks | Blocks may appear in any order after `begin`. A loop is what the declarations say. A jump to a block `within H` is legal only from `H` or from a block inside `H`. Every cycle must pass through a declared header. |
| A20 | `in` was glossed "owned by" beside `ownedBy`; an instantiated list was `is record`; `with<Field>` changed case; "no dots" sat beside `Token.new` | `in` means "belongs to". An instantiation is `<Name> is instance`. Field update is `<Record>.with` (A10). Dots appear only in paths: `module.name`, `Type.target`, `Enum.variant`. |
| A21 | Table row order was semantic but positional | `<table> row <rowId> <position>` declares each row and its order. Cells name a declared row. |
| A22 | Context rows came first on operations and last on everything else | On every entity kind, context rows come directly after the `is` row. |
| A23 | Whether `arg`, `set`, and `return` accept literals was unstated, which gives two spellings | Literals appear only in `let` rows and table `cell` rows. Everything else takes a name. |
| A24 | A region only empties at `return`, so a loop that allocates grows without limit; what a trap does to cleanups was unstated | A loop body that allocates is its own operation with its own region. A trap runs the deferred cleanups of every operation on that task's stack, then ends the task; its owner sees a `trapped` failure. |
| A25 | Whether console calls wait, and which loop kind reads to end of input, were guesses | `console.readLine` waits, so it is a task. Console writes are `do`. End of input is an error variant, inspected with `match`. A loop over input of unknown size is `forever`; a `forever` loop may have exits. |
| A26 | Slot and error names had to be guessed | Library conventions: slots `left`/`right` for two operands, `value` for one, `text`, `index`, `list`/`item`, `record`, `payload`, `region`. Error enums are `<module>.<Thing>Error`. Every module publishes its targets, slots, errors, and effects in its signature, and tooling lists them. |

### Not adopted

- **A per-iteration region reset step.** It would need the checker to prove no
  value from the region is still in use. The separate-operation idiom (A24) is
  explicit and already works.

### What the examples now cover

`tokens.sem` and `tokens.test.sem` were added because the reviewer showed the
first two examples avoided most of what a compiler needs. Together the four
files now use: an instantiated list, `lendMutable`, an operation that `raises`,
`return error`, an error payload, `match` / `case`, `Option`, a fallible list
read, a `while` loop bounded by a run-time value, `forEach`, `forever`, a task
group, an operation reference, and a test with `verifies`.

Still not exercised by any example: `Map`, `Set`, `counted` and `doWhile`
loops, `give` of a region-owned value, `cancel`, channels, and file I/O.

## Part 4: implementation (2026-11-13)

Superseded in part by Part 5: the bridge described here was removed, and every
item in "Not enforced yet" is now enforced.

Work on the compiler started from this file on 2026-11-13. This part records
how it is built, what it enforces today, and the decisions made while building
it. Decisions marked D-n were made by delegation, the same way as Parts 2 and 3.

### Approach

The refined syntax changes almost every row, so it is implemented as a new
front end beside the legacy compiler rather than inside it:

- `semanticscript/compiler/refined/` holds the lexer, the shape table
  (`shapes.py`), the parser, the checks (`semantics.py`, `flow.py`), the
  standard-library signatures (`library.py`), and a lowering bridge.
- The bridge (`lower_legacy.py`) turns a checked program in a small runnable
  subset into legacy rows and runs it on the existing LLVM backend. Anything
  outside the subset is refused with `R901`; nothing is silently dropped.
- The legacy compiler (`semanticscript.py`) is unchanged. It retires once the
  corpus is migrated (plan step 10) and the refined front end has its own
  backend.

Commands:

```
python semanticscript/compiler/refined check <module.sem | build.sem | project dir> [--json]
python semanticscript/compiler/refined run   <build.sem | project dir> [--json]
python semanticscript/compiler/refined lower <build.sem | project dir>
python semanticscript/compiler/refined grammar
```

`docs/refined-grammar.md` is generated by `grammar` from the shape table.

### Worked examples, now checked by the real checker

| Project | What it shows | Status |
| --- | --- | --- |
| `docs/refined-examples/hello` | Hello world | checks clean, runs: `Hello, world!` |
| `docs/refined-examples/sum` | A `counted` loop | checks clean, runs: `15` |
| `docs/refined-examples/factorial` | Recursion with `maxRecursion` | checks clean, runs: `120` |
| `docs/refined-examples/server` | HTTP server: tasks, a task group, a cleanup, regions, a route table, an operation reference | checks clean; not runnable yet (R901) |
| `docs/refined-examples/selfhost` | Lexer and tokenizer in two modules, a generic list, `match`/`case`, `Option`, a test file | checks clean; library project |

The sketch checker `tests/audit/refined_sketch_lint.py` is retired; the real
checker replaces it.

Writing the checker found mistakes the sketch checker had passed: the lexer
example never exported the `Token` and `TokenKind` types that the tokenizer
imports, and two calls passed plain records by loan.

### Tests

`tests/test_refined.py` (74 tests):

- every worked example checks clean, and the three runnable ones print the
  expected output;
- the server is refused by `run` with `R901`, not half-run;
- one test per rule: copy a clean example, introduce exactly one mistake,
  assert the rule's code is reported;
- a guard that fails if any diagnostic code has no such test.

### What is enforced today

| Rule | Source | Code |
| --- | --- | --- |
| Lexical rules: whitespace, control characters, strings, quotes, `#` | LR-11, A23 | R101-R106 |
| An entity's rows follow its `is` row without interruption | D-14 | R201 |
| Known kinds, unique names, case by kind, reserved words | A5, D-3 | R202, R203, R206, R207 |
| Every predicate allowed on its kind, with its exact shape | LR-09, LR-18 | R204, R205 |
| Skeleton order, exactly-one and one-or-more rows, `none` alone | LR-18, A1, A13, A22 | R301-R303 |
| `purpose` where required, invariants on operations only, filler text | LR-06, A17, D-4, D-5 | R304 |
| Every block declares `loopKind` and `within`, in block order | A13, D-6 | R305 |
| Tables: declared rows, every cell exactly once, typed values | LR-26, A21 | R306 |
| Every name resolves, to the right kind | LR-02, LR-32 | R401, R402 |
| Imports: prefixed names, no unused or missing imports, exports | LR-32, A3 | R404 |
| Types agree everywhere a row states one | LR-05 | R403 |
| Arguments match the target's parameters, in order, with paired modes | LR-31, D-7, D-8 | R405, R406 |
| `out`, `catch`, `ownedBy`, `borrows`, `cleanedBy` agree with the target | LR-20, LR-31 | R403, R409 |
| A cleanup's call takes the cleaned value with `give` | LR-20 rule 6 | R409 |
| Declared effects equal performed effects, transitively | LR-07, D-11 | R407 |
| Every effect granted by a used capability; no idle capabilities | LR-07 | R408 |
| `async`, `memory heap`, `maxRecursion` state exactly what the code does | D-11 | R410 |
| A waiting target is a task | LR-33 | R410 |
| One namespace per operation | LR-02, D-15 | R411 |
| Blocks: contiguous, `begin` first, one terminator, `match`/`case` | LR-16, A6, A13 | R501 |
| Jumps go to existing blocks; every block reachable | LR-16 | R502, R511 |
| Loop facts belong to loop headers; bounds stated; `forEach` shape | LR-22, LR-23 | R503 |
| Single entry into loops; every cycle passes a declared header | LR-23, A19 | R504 |
| A counted loop sets its counter exactly once on every pass | A14 | R505 |
| A fallible `do`/`join` is followed at once by `branch ifError` | LR-16, LR-30 | R506 |
| Each call, task, and cleanup activated the right number of times | D-10 | R510 |
| Every value set on every path that reads it, with types checked at each use | LR-04, LR-29, A4 | R507 |
| `return ok` / `return error` agree with `output` and `raises` | LR-30 | R508 |
| `match` covers every variant once; bindings mirror payloads | A6, D-9 | R509 |
| Tasks and task groups settled on every path to a return | LR-33, A12 | R512 |
| build.sem, module file locations, import cycles, `verifies` targets | LR-32, D-13 | R601-R604 |

### Not enforced yet

Each line is a rule from this file that the checker does not yet check. Until it
does, the rule is a stated fact that is not verified, so closing these is the
next work.

1. **Per-path ownership.** An owned value is released, given, or returned
   exactly once on every path (LR-20 rule 6). Today: only "given or returned
   somewhere" when `cleanedBy none`.
2. **Use after `give`**, and borrowed values that are stored or returned
   (LR-20 rules 6 and 8).
3. **Every invariant is verified by a test** (LR-06 rule 3). Today only that
   each `verifies` names a real operation and invariant.
4. **`maxIterations` equals a constant trip count**, and the `counted` header
   tests its counter against an immutable limit (A14).
5. **Run-time enforcement** of `maxIterations` and `maxRecursion`. The bridge
   runs programs without these traps.
6. **Staleness flag** for context rows (LR-06 rule 4).
7. **Capability `scope`** against literal arguments (LR-34 rule 5).
8. **`<Record>.with`**, generic operations, and `typeParam` constraints
   (LR-24, LR-28).
9. **Library signatures** for `map`, `set`, `buffer`, `fs`, `process`, `clock`,
   `environment`, and channels (LR-40). Today `library.py` covers what the
   worked examples use.
10. **A backend** for regions, tasks, records, enums, tables, and errors. The
    bridge runs only the plain subset.

### Decisions made while implementing

- **D-1** The refined front end is a separate package; the legacy compiler
  retires after the corpus migrates.
- **D-2** Every record and enum states `typeParam none` when it is not generic,
  and every alias states `indexes none` when it indexes nothing. Same reason as
  A1 and A13: no fact by absence.
- **D-3** Type names (records, enums, aliases, instances, operation types) start
  upper-case; every other name starts lower-case.
- **D-4** `invariant` rows live only on operations. A test's `verifies` names
  an operation, so an invariant anywhere else could never be verified; this
  resolves a conflict between LR-06 rule 1 and A17.
- **D-5** Context rows come in a fixed order: `purpose`, `invariant`,
  `verifies`, `rationale`, `risk`, `note`, `todo`, `deprecated`.
- **D-6** Label rows are grouped per label, in the same order as the blocks,
  each label's facts in the order `loopKind`, `within`, `maxIterations`,
  `counter`, `over`, `because`, then its context rows.
- **D-7** Arguments appear in the target's parameter order.
- **D-8** The passing mode follows the type. Plain values are `value` / `copy`
  (including reading a field of a plain record); a `Region` is always
  `borrowed` / `lend`; non-plain values are `borrowed`, `borrowedMutable`, or
  `owned`.
- **D-9** A `case` binding mirrors its variant: `bind none none` exactly when
  the variant has no payload. A payload is always bound, even if unused.
- **D-10** A task started into a task group is settled by the group: it is not
  joined itself, and it states `out none` and `catch none` because its result
  cannot be read.
- **D-11** Declared facts are exact in both directions: an `effect` row with
  nothing behind it is as wrong as a missing one, and likewise `async true`,
  `memory heap true`, and `maxRecursion <n>`.
- **D-12** Tests live in `<module>.test.sem` beside the module and are part of
  it; the module imports what its tests use (for example `standard.test`).
- **D-13** `build.sem` holds one `project` entity: `target console|library`,
  one `module <path>` row per module, and `entry <module>.<operation>` or
  `entry none`. A module with path `a.b` lives in `a/b.sem` beside build.sem.
- **D-14** An entity's rows follow its `is` row without interruption.
- **D-15** Within one operation, labels, values, and owned entities share one
  namespace, and none may reuse a module-level name.

## Part 5: everything enforced, own backend (2026-11-13)

The owner asked to enforce every rule Part 4 listed as not enforced, to keep
going, and then: **no bridge, no backwards compatibility.** This part records
what changed. Where it conflicts with Part 4, this part wins.

### Direction

- **No bridge.** The lowering to the earlier compiler is deleted. The refined
  compiler generates LLVM IR from its own checked model
  (`semanticscript/compiler/refined/codegen.py`) and runs it with its own JIT
  runtime (`runtime.py`). It imports nothing from `semanticscript.py`.
- **No backwards compatibility.** Nothing is kept or built to stay compatible
  with the earlier syntax. Plan step 10 (migrate the corpus) is replaced by:
  *remove the earlier compiler, its 245 examples, its tests, and its CI lanes,
  and point CI, packaging, and the editor extension at the refined compiler.*
  That removal has not been done yet.
- The library table no longer carries names from the earlier backend.

### Commands

```
python semanticscript/compiler/refined check   <module.sem | build.sem | dir> [--json]
python semanticscript/compiler/refined run     <build.sem | dir> [--json]
python semanticscript/compiler/refined test    <build.sem | dir> [--json]
python semanticscript/compiler/refined emit-ir <build.sem | dir> [--test MODULE.TEST]
python semanticscript/compiler/refined stale   <path> --base <git revision> [--json]
python semanticscript/compiler/refined grammar
```

`test` runs each test in its own process, so a trap ends only that test, and
reports PASS, FAIL (with the failed assertions), TRAPPED (with the trap
message), or UNSUPPORTED (with the backend's R901 diagnostic).

### Part 4's open list, closed

| # | Rule | Now |
| --- | --- | --- |
| 1 | Owned value released, given, or returned exactly once on every path | Enforced: a per-path analysis tracks each owned value as not acquired, owned, under a deferred cleanup, or given. Leaks at a return, a second acquisition over a live value, giving a value under a cleanup, and returning it are R513. |
| 2 | Use after `give`; borrowed values stored or returned | Enforced: R513 for use after give; R514 for giving or returning a borrowed input or a view; R515 for exclusive loans of shared or read-only values. |
| 3 | Every invariant verified by a test | Enforced (R604). |
| 4 | Counted-loop header shape and exact constant trip count | Enforced (R505); see D-23. |
| 5 | Run-time `maxIterations` and `maxRecursion` | Enforced by the backend; both trap with a message naming the source. |
| 6 | Staleness flag | `refined stale` (R605); see D-17. |
| 7 | Capability scope | Enforced (R408); see D-22. |
| 8 | `Record.with`, generic operations, type-parameter constraints | Enforced; see D-18 to D-20. |
| 9 | Library signatures | Added for console, math, compare, bits, convert, string, byte, buffer, time, clock, environment, process, fs, net, http, list, map, set, option, channel, test. |
| 10 | A backend | The refined compiler's own LLVM backend; coverage below. |

### Backend coverage

Runs today: integers with overflow and division traps, `Byte`, `Bool`,
`ExitCode`, `Float64`, `String` literals, records, enums (payloads that are
integers, `Bool`, `Byte`, or payload-less enums), tables walked by `forEach`,
`match`/`case`, operations that raise and `return error`, `branch ifError`,
operation references, recursion with `maxRecursion`, loops with
`maxIterations`, regions (arena with enforced capacity, freed at return),
`list.List`, `option.Option`, cross-module calls, and these library targets:
`math`, `compare`, `bits`, `convert`, `console` writes, `string.byteLength`,
`byteAt`, `equals`, `startsWith`, `byte`, and `test`.

Refused with R901 for now: tasks, task groups, and every target that waits
(`net`, `fs` reads and writes, `console.readLine`, `time.sleep`, `channel`);
cleanups and `defer`; generic operations and `operationInstance`; strings
allocated at run time (`string.concat`, `fromInt64`, `fromBytes`, `buffer`);
`map`, `set`; `process`, `clock`, `environment`; `http`.

Worked examples:

| Project | Check | Run / test |
| --- | --- | --- |
| hello | clean | runs: `Hello, world!`; 1 of 1 tests pass |
| sum | clean | runs: `15` |
| factorial | clean | runs: `120`; 1 of 1 tests pass |
| selfhost (lexer, tokenizer) | clean | 5 of 5 tests pass |
| server | clean | refused: tasks are not supported yet |

### Tests

`tests/test_refined.py` has 96 tests, all passing: every worked example checks
clean; every rule code has a test that breaks a clean example and gets that
code; generic operations and `Record.with` check clean and fail on misuse;
`stale` flags a structural change without a prose change; the example tests
pass on the backend; the backend reports a wrong expectation as FAIL with the
values and a low loop bound as TRAPPED with the loop named; `run --json`
captures output.

### Decisions in this pass

- **D-16** A project's entry operation may state `invariant none`. Its
  behavior is the whole program's, checked end to end, not by a unit test.
  Every other exported operation still makes a tested claim.
- **D-17** The staleness flag is a command, not a compile error: `stale`
  compares with a git revision and exits 1 when it flags anything. An author
  re-confirms unchanged prose by adding a `note` row that says why it still
  holds.
- **D-18** Every operation states `typeParam` (`none` when not generic), for
  the same reason as D-2. A generic operation is called only through an
  `operationInstance` entity (`<name> instantiates <operation> <Type>...`),
  never directly. A test is never generic.
- **D-19** A type parameter's constraint is part of its type: `plain`
  parameters are copied (`value`), `any` parameters are borrowed. An
  instantiation whose argument breaks a `plain` constraint is an error.
- **D-20** `<Record>.with` takes `record`, then exactly one slot named by the
  field it replaces.
- **D-21** The backend's runtime surface is a fixed set of callbacks (output,
  byte comparison, traps, test assertions, regions). A trap writes
  `trap: <file>:<line>: <message>` to standard error and exits with code 70.
- **D-22** Scoped resources are `net.tcp` (scope `"<address>:<port>"`, checked
  against the port), `net.outbound` and `fs.files` (scope is a prefix), and
  `process.programs` (scope is the exact program). A capability's grants are
  all scoped the same way; everything else is `scope none`.
- **D-23** A counted loop's header is `do <check>` then `branch if <result>`,
  where the check is `compare.lessThanInt64`, `lessOrEqualInt64`,
  `greaterThanInt64`, or `greaterOrEqualInt64` of the counter against an
  immutable limit. The single `set` of the counter takes the result of
  `math.addInt64` or `math.subtractInt64` with the counter as `left` and an
  immutable non-zero step as `right`. The counter must move toward the exit,
  and when the start, limit, and step are all literals, `maxIterations` must
  equal the number of passes.

### Next

1. Remove the earlier compiler and switch CI, packaging, and the editor
   extension to the refined compiler (the replacement for plan step 10).
2. Backend: cleanups and `defer`, run-time strings in regions, `map` and
   `set`, then tasks and task groups on a cooperative scheduler, then `net`
   and `http` so the server runs.
3. A formatter (`fmt --check` is part of the strict gate, LR-01) and the editor
   grammar generated from the shape table.
4. Plan step 12: the agent-writability evaluation, now that a model's program
   can be checked, run, and tested end to end.

## Part 6: the earlier compiler removed (2026-11-13)

At the owner's request ("remove it"), everything that belonged to the earlier
toolchain was deleted. There is no compatibility layer and no migration; the
code remains in git history before this change.

Removed:

- the earlier compiler (`semanticscript/compiler/semanticscript.py`), its
  standard library (`semanticscript/std`), signatures (`semanticscript/sigs`),
  C runtime (`semanticscript/runtime`), and packaging;
- `examples/` (245 programs), `apps/`, `experiments/`, and `legacy/`;
- vendored third-party C sources (`third_party/`: sqlite, libuv, bcrypt, and
  the h2o and emsdk submodules), which only the C runtime used;
- the earlier test suite (every file in `tests/` except `conftest.py`), the
  audit scripts in `tests/audit/` (they measured the earlier compiler; the
  explicitness-audit numbers below are kept as history), and the coverage
  config;
- the earlier docs: `LANGUAGE.md`, `GRAMMAR.md`, `ROADMAP.md`,
  `GOVERNANCE.md`, `getting-started.md`, `todos.md`, `defect-ledger.md`,
  `security-matrix.md`, `design-bounds-carrying-buffers.md`, and
  `human-authoring-validation.md`;
- CI workflows for the earlier toolchain: compiler executable, native safety,
  runtime platform, release, and the project website.

Changed:

- **CI** (`.github/workflows/ci.yml`) runs the refined test suite on Windows
  (Python 3.11 and 3.12) and Linux, checks every worked example, and fails if
  `docs/refined-grammar.md` or the editor grammar is out of date. The Windows
  job names are unchanged, so the branch-protection checks still match. A
  separate job checks the editor extension. CodeQL analyzes Python and
  JavaScript only.
- **Editor extension** rewritten (about 150 lines, from 5,800): its grammar is
  generated from the shape table (`refined grammar --textmate`), diagnostics
  come from `refined check --json` on save, and it has Check, Run, and Test
  commands and skeleton snippets.
- **README, CONTRIBUTING, CHANGELOG, THIRD_PARTY_LICENSES** describe the refined
  compiler only. Dependabot watches pip, GitHub Actions, and the extension.
- Plan step 10 (migrate the corpus) is done by removal; plan step 1's promise
  that one table drives the parser, the grammar reference, and the editor
  grammar is now true.

Not done: a release workflow and packaged binary for the refined compiler, and
a Marketplace publisher for the extension.

## Part 7: the test suite (2026-11-14)

The owner asked for a clear and powerful test suite, aligned with the language,
covering positive, negative, and edge cases, to find and fill gaps. It lives in
`tests/suite` and runs as `tests/test_suite.py`; `docs/test-suite.md` is now a
generated coverage map of the owner's checklist (456 items), each with a status
and the cases that prove it.

What it holds:

- **Program cases** (`tests/suite/programs`, one directory per checklist
  section): complete programs whose header comments state what they cover and
  what must happen: check clean, run with exact stdout, stderr and exit code,
  trap with a message, pass or fail their tests, or be refused by the backend
  with R901 (`unsupported`, so the case fails the day the backend learns the
  feature).
- **Mutations** (`tests/suite/mutations.py`): one deliberate mistake in a
  passing case and the exact set of rule codes it must produce. Every rule code
  except R605 (needs git history) and R901 has at least one.
- **Generated tests**: stress (2,000 values in one operation, a chain of 1,000
  operations, 300 nested decisions, a 200,000-byte string, recursion 200,000
  deep, a 500,000-item list, 40 modules in a chain), fuzz (random damage to
  every single-file case must give diagnostics with known codes and real lines,
  never an exception), differential (random `math` and `bits` arithmetic
  against a Python model, traps included), determinism, source locations, and
  the CLI.

What it found, and what changed:

| Found | Kind | Fix |
| --- | --- | --- |
| A row that broke its shape (`main let ten immutable 10`) crashed the checker with an `IndexError` | checker crash | Rows are reported, then dropped before later passes; a malformed row only ever produces diagnostics |
| A nested counted loop could not restart its counter: only the loop may set it, so the inner loop of `for i, for j` was inexpressible; entering an inner loop from its outer loop was also reported as a jump back (R504) | language gap | D-24 below; the R504 back-edge test stops at the headers of enclosing loops |
| `string.slice` with a huge length overflowed `start + length` and passed the bounds check, giving a view far past the end of the string | memory safety | The check compares without forming the sum |
| Recursion within a large stated `maxRecursion` overflowed the native stack and killed the process with no message | safety | D-25 below |
| `math.powerInt64` multiplied once per unit of exponent, so `1` to the power `10^18` effectively never finished | denial of service | Square-and-multiply: at most 63 rounds; same overflow traps |
| `math.saturating*Int64` passed the checker but the backend refused them | backend gap | Implemented |
| A project module named like a standard module (`clock`) produced a self-import cycle and misleading errors | language gap | D-26 below |
| A call into a project module that failed to load said "the standard module `area` has no target" | diagnostic | Says the module is not part of the project |
| A reserved word or an upper-case name in a `let` gave only a generic shape error | diagnostic | R206 and R207 name the slot when it is the only thing wrong |
| `run` on a lone module file reported that module's other errors instead of "needs a project" | CLI | `run`, `test`, and `emit-ir` report the missing project first |

Decisions (by delegation):

- **D-24** A counted loop's counter may also be set by a block outside the loop
  when that block enters the loop directly (its last step is `goto <header>`)
  and sets the counter from an immutable `Int64` let. The constant trip count
  is computed for every such start value, and `maxIterations` states the
  largest, counted per entry. This is how a nested counted loop restarts.
- **D-25** Compiled code runs on its own thread with a 128 MiB stack. Every
  operation with a `maxRecursion` bound checks, on entry, that more than 8 MiB
  of that stack remains, and traps with "ran out of stack before reaching
  maxRecursion N" when it does not. `maxRecursion` is still the declared bound;
  the stack check makes an unrealistic bound a clean trap instead of a crash.
- **D-26** A project module may not take the name of a standard module (R602),
  since `<name>.<target>` would be ambiguous.

Open work is listed at the end of `docs/test-suite.md` (every `gap` and
`static` item). The largest: tasks, cleanups, `map` and `set`, generic
operations, and the host-I/O modules do not run in the backend yet; there is no
foreign function interface, formatter, language server, debugger support, or
package versioning.

## Part 8: everything compiles and runs (2026-11-14)

The owner asked to compile and run every program. Before this part, twelve
suite cases and the server example were refused by the backend (R901). Now
every positive and edge program in the suite runs (a test enforces it), every
worked example runs or passes its tests, and the server answers real HTTP
requests.

What the backend gained:

- **Generic operations**, compiled once per set of type arguments an
  `operationInstance` names (direct calls and operation references).
- **Cleanups and `defer`**: an armed cleanup runs at every later `return`,
  newest first, at most once; `onFailure trap` traps if its call fails.
- **Tasks, task groups, channels, async operations** (D-27, since replaced by D-31).
- **Host targets** through one callback (D-28): `console.readLine`,
  `time.sleep` and deadlines, `clock`, `environment`, `process` (arguments and
  running programs), `fs`, `net`, `http`, `buffer`, `string.fromBytes`, and
  `map`, `set`, and `channel` values.
- `string.toBytes` (a view, no copy); `Bytes` values; handles for resources
  and host-kept values; `refined run PATH -- <arguments>`.

Decisions (by delegation):

- **D-27** (replaced by D-31 below) Tasks run eagerly: `start` runs the task to completion, in program
  order, on the program's thread; `join`, `cancel`, and `awaitSlot` then have
  nothing to wait for. Programs written for real concurrency stay correct
  (the checker's structure rules are unchanged), and runs are deterministic.
  The cost: nothing overlaps, and a channel wait that only another task could
  satisfy cannot be satisfied. Such a wait traps as a deadlock when it has no
  deadline, and waits the deadline out (then fails with `timedOut`) when it
  has one. A real scheduler can replace this without changing the language.
- **D-28** Library targets that need the operating system are lowered to one
  runtime callback, `refined_host`. Arguments are flattened into 64-bit slots
  by machine type (an integer is one slot, a string or byte string is pointer
  and length, an enum is tag and payload, a record is its fields), and the
  runtime dispatches by target name (`semanticscript/compiler/refined/host.py`).
  Values the host keeps (files, sockets, maps, sets, channels, buffers,
  argument lists, responses) are integer handles. A handle made in a region is
  dropped when the region is released; using a dropped or closed handle traps.
- **D-29** `net.listen` binds the host named in the scope of the capability
  that grants `listen net.tcp`. The server example's scope is now
  `"127.0.0.1:8080"`, so running it never opens a port to the network;
  widening the scope is the explicit way to serve beyond loopback.

- **D-30** An enum whose payloads are all integers, `Bool`, or payload-free
  enums keeps the compact layout `{tag, 64-bit payload}`. Any other enum (an
  `option.Option String`, a variant carrying a record, a list, or another such
  enum, an error carrying a message) has a wide layout: the tag, then one field
  per variant that carries a payload. `equals` is structural for every type:
  records field by field, enums by tag and the active payload, lists element by
  element, text and bytes by content, host values by identity.

- **D-31** (replaces D-27) Tasks run in parallel. `start` fills a frame with
  the task's arguments and hands the runtime a generated thunk that runs the
  task on its own thread; `join` waits and reads the results back from the
  frame. A task group runs at most `limit` tasks at once; `awaitSlot` waits for
  room, and starting into a full group traps (A12). Cancellation is
  cooperative and reaches every task a cancelled task started: waits on
  channels, sleeps, accepts, and socket reads end with `cancelled`; pure
  computation runs to its end, and `cancel` waits for the task to stop. When
  every task waits on another with no deadline, the program traps and names
  each wait. Recursion depth and the stack floor are kept per thread.
- **D-32** `fs` gains `openAppend` (write at the end, creating the file if
  missing), `createDirectory`, `removeDirectory`, and `listDirectory` with
  `entryCount` and `entryName` (names in sorted order, region-owned).

Nothing a clean program can contain is refused any more. R901 stays as a guard:
a library target the backend does not implement is refused by name, never
miscompiled (`test_unknown_library_target_is_refused_not_dropped`). The suite
proves the rest: every operation and test of every program and worked example
compiles (`test_every_operation_compiles`), every program case runs
(`test_every_program_case_runs`), and a tour calls every standard-library target
no other case uses (`tests/suite/programs/19-stdlib/library-tour.sem`).

## Part 9: the checklist closed (2026-11-14)

After Part 8 the coverage map still listed 44 gaps. All but one are now
implemented and tested; `docs/test-suite.md` has the evidence for each.

- **Library:** `random`, `crypto`, `log`, `json` (parse, typed access, build,
  `stringify`), `secret`, `signal`, `fs.lock`/`unlock`, `fs.openAppend` and
  directory operations, `process.runCaptured` (pipes).
- **Runtime:** parallel tasks (D-31); a trap prints the chain of callers.
- **Tooling:** `refined fmt`, `repl`, `lsp`, `bench`, a build cache, and
  `run --trace`, `--coverage`, `--profile`, `--debug --break`.
- **Native:** `refined build` emits objects or assembly for any LLVM target,
  or WebAssembly that `tests/suite/wasm_host.mjs` runs in Node.
- **Interop:** the `ffi` module.
- **Packages:** versions and local packages in build.sem.

Decisions (by delegation):

- **D-33** A new effect verb, `load`, for bringing native code into the
  process. `ffi.open` needs `load ffi.libraries`, scoped by library name.
  A foreign function's type is an `operationType` over numbers and `Bool`
  that raises nothing, waits for nothing, and has no effects; only values the
  C ABI passes as they are cross, so no memory is shared across the boundary.
- **D-34** build.sem states `version "<MAJOR.MINOR.PATCH>"`, `language
  refined-1`, `standardLibrary 1`, and `requires <name> "<path>"
  "<constraint>"` (or `requires none`). A required project is a library whose
  version satisfies the constraint; its modules are imported as
  `<name>.<module path>`. Requirement cycles are R603.
- **D-35** A `secret.Secret` has no route back to text but `reveal`, which
  needs `read secret.values`; a program that must not leak a value keeps it a
  Secret.
- **D-36** The formatter changes layout only: token spacing, blank lines
  between entities, the space before a trailing comment. Comment text is
  kept exactly.

- **D-37** `refined build --kind executable` links the program's object, a C
  runtime (`native_runtime.c`: output, regions, traps with stack traces, the
  call stack, recursion and stack guards, tasks run when started), and a
  generated `main` with the system C compiler, statically where the platform
  allows. Library targets that need the operating system host stay in the JIT
  runtime; in an executable they trap with the target's name.

Every checklist item now has evidence or a stated reason.

## Part 10: adversarial refinement (2026-11-14)

An adversarial critic was asked to break the language: to write programs the
checker accepts but that are wrong, and to find rules that are vague,
inconsistent, or unenforced. Each round's findings were fixed, then the critic
ran again. Findings fixed in the first round:

- Loans to tasks: a task holds every loan it was given from `start` to `join`
  (D-39). Giving, setting, or lending mutably a value a running task holds is
  R515; so is changing a collection inside a `forEach` over it.
- Task lifetime: starting a task that may still be running (for example in a
  loop with the join after it), joining twice, and joining or cancelling a
  task that is not running are R510.
- Scope checks: a network scope is a prefix only up to a `:` or `/` boundary,
  so `"api.test"` no longer admits `"api.test.evil.example"`. A literal path
  with a `..` component is R408.
- Tests: a test that `verifies` an operation it never calls, or that calls no
  `test.` assertion, is R604.
- A cleanup whose call is not the `cleanedBy` of the value it releases is R409.
- A malformed row no longer also reports its predicate as missing (R302).

Decisions (by delegation):

- **D-38** Capability scopes are enforced again at run time: a scoped argument
  that is computed, not a literal, is checked before the call against the
  scopes of the capabilities the operation uses, after `..` and links are
  resolved. Outside every scope is a trap naming the argument and the scopes.
- **D-39** A task's loans last from `start` to `join` (or `cancel` then
  `join`); the collection of a `forEach` is lent for the whole loop.
- **D-40** A `let` initialized from a name copies only plain values (R514); a
  second name for a String, list, or record would carry a borrow past its
  loan. A resource (a file, a socket, a library) cannot be stored in a
  collection (R403), because a region releases a collection without closing
  what is in it. `ExitCode` is 0 to 255, what every platform delivers.
  `secret.matches` and `secret.length` need `read secret.values`, since both
  reveal something about the secret. `fs.close` needs no authority beyond
  owning the handle. A standalone executable is refused (R901) when the
  program calls a host-library target, instead of trapping when it runs
  (amends D-37).
- **D-41** build.sem states the program's whole authority in `allows` rows,
  the same `<verb> <resource> <scope>` triples capabilities grant
  (`allows none` when it needs none). Every capability in every module grants
  only what an `allows` row covers, with a scope inside the allowed one
  (R408). A required package states what it needs in its own build.sem, and
  the program requiring it must allow that too, so the project file is the
  one place to audit what a program may do. A foreign function is authorized
  by name: binding needs `load ffi.symbols` scoped to that symbol. An
  `fs.files` scope says which kind it is: a directory ends in `/`
  (`"data/"`: anything inside it), a name pattern ends in `*` (`"suite-*"`:
  entries of the current directory whose names start with `suite-`). Any
  other scope is R408. Tools that write a build.sem for code they did not
  write (the REPL, the test harness) derive the `allows` rows from the
  capabilities in it.
- **D-42** Every error a waiting target raises has a `cancelled` variant
  (`console.ReadError`, `process.RunError`, `fs.FileError`), and every wait
  honours its deadline: `readLine` and child processes stop waiting at the
  deadline or on cancellation, and a file read or write made after its
  deadline, or by a cancelled task, does not start. A negative duration given
  to `time.Deadline.after` or `time.sleep` traps instead of counting as zero.
  `process.runCaptured` output larger than `maxBytes` is
  `process.RunError.tooLarge`, not a numbered `failed`.

- **D-43** A target that changes the state of the handle it is given (a
  file's position or lock, a connection's stream, a listener's queue) takes
  it `borrowedMutable`: `fs.read`, `fs.write`, `fs.lock`, `fs.unlock`,
  `net.accept`, `net.read`, `net.write`. Two activations can never use one
  handle at once. A channel stays a shared loan: it is a synchronized queue
  that exists to be used by several tasks.
- **D-44** `cancel` asks a task (and every task it started) to stop and
  returns at once; `join` waits for it and delivers its outcome. Every
  started task is joined on every path, cancelled or not, and its loans last
  until that `join`. There is no detached task. (Replaces the part of D-31
  where `cancel` waited.)
- **D-45** A `forEach` over a table states a `maxIterations` at least the
  table's row count, checked when the program is checked; over a list,
  passing the bound traps at run time.
- **D-46** Capabilities are never exported (R402).

- **D-47** One pattern for the whole syntax (the owner: "don't simplify
  syntax, make sure it has a consistent pattern"). Nothing becomes implicit;
  rows that said the same thing two ways now say it one way:
  - one word for "why": `rationale` (the cleanup row and the `forever` label
    fact `because` are gone; every cleanup states a `rationale` context row);
  - context rows lead everywhere: a label's `purpose`/`rationale`/`risk`/
    `note`/`todo` come before its `loopKind`, as an entity's do after `is`;
  - `let <name> <Type> <value> <mutability>`, slot for slot like
    `argument <slot> <Type> <value> <mode>`, and `let none` when there are
    none (every `some` predicate states `none` rather than being absent);
  - `grants <verb> <resource> <scope|none>`: each grant carries its scope,
    the same triple as `allows` (the capability `scope` row is gone);
  - parameter modes `copied`/`borrowed`/`borrowedMutable`/`owned` pair with
    argument modes `copy`/`lend`/`lendMutable`/`give`;
  - single-word predicates: `memoryHeap`, `outputOwnedBy` (beside `ownedBy`),
    `onError` (errors are never called failures), `runs` for a cleanup's call;
  - bounds are `max<Thing>`: `maxIterations`, `maxRecursion`, `maxBytes`
    (region), `maxTasks` (task group);
  - full words: `argument`, `result`, `typeParameter`;
  - `start <task> into <group|none>` always states its group;
  - type kinds alike: `typeInstance` (beside `operationInstance`),
    `aliasOf`, `rowType`, and `typeParameter` on every type kind; `alias`
    states a `purpose`;
  - build.sem: `includesModule <path>` (a kind name is no longer a
    predicate) and `language refined 1` (a name and a number, like
    `standardLibrary 1`).
  Not changed, on purpose: `raises`/`uses` keep their verbs, and loop-only
  label facts stay on loop headers. Rows in Parts 1 to 10 show the syntax of
  their time; `docs/refined-grammar.md`, generated from the shape table, is
  the current reference.

- **D-48** Failure propagates through task groups. A group states the one
  error type its tasks raise (`<group> catch <name> <Type>`, or `catch
  none`); a fallible task may be started into it only if it raises that type
  (R403). The first task to fail records its error in the group and cancels
  the group's other tasks; `join <group>` waits for every task and delivers
  that error, and is followed directly by `branch ifError <group>` (R506).
  Later failures are dropped, since every task already stopped for the first.
  (Replaces D-10's rule that grouped tasks state `catch none`.)
- **D-49** Running out of a region is a safe trap, not a typed error. The
  trap happens before any memory is written and names the region and its
  capacity. A typed error would make every allocating target fallible,
  so every string, list, and read would need an error branch for a limit the
  program states itself; the program sizes its regions instead. (The goal's
  item 6 allows typed errors or safe traps; this is the second.)
- The authoring-syntax items of the same goal (inferred defaults, a concise
  syntax over the rows) were replaced by the owner's instruction "dont
  simplify syntax, make sure it has a consistent pattern"; D-47 is that
  consistency pass.

The guarantees these rules add up to are stated, with the executable checks
that prove each one, in `docs/safety-guarantees.md`, generated from
`tests/suite/conformance.py`.

The `warehouse` example (`docs/refined-examples/warehouse`) uses these rules
together: build.sem `allows`, a scoped file capability, a table loaded into
a list, operation references, two tasks borrowing one list, cancellation on
the failure path, a cleanup that traps, exhaustive matches, and a test per
invariant.

## Explicitness audit (2026-11-13)

Measures the current compiler against P-2.

### Method

For each row in the examples, apply one mutation and run `check --strict`:

- **DEL**: delete the row (not applied to `is` rows).
- **DROP**: remove the row's last token.
- **ADD**: append a junk token (`zzExtraToken`).
- **DUP**: repeat the row on the next line.

A mutation is "accepted" if the check still reports `ok: true`. Up to 12 rows
were tested per (kind, predicate, mutation). The audit scripts were removed in Part 6 along with the compiler they measured;
they are in git history before that change.

### Coverage

- 224 of 243 examples pass `check --strict` unmodified and were used.
- 2,682 checks over 73 (kind, predicate) pairs.
- The compiler's `ALLOWED_PREDICATES` table has 259 structural pairs across 23
  kinds; the usable examples exercise 59 of them. Ten kinds have no coverage:
  `errorCase`, `function`, `htmlTemplate`, `intrinsic`, `platform`, `region`,
  `semsig`, `sharedState`, `typestate`, `webServer`.
- So these results are a floor. Most of the vocabulary has no strict-clean
  example to test against, which is itself a gap.

### Results

| Mutation | Predicates accepting it | What it means |
| --- | --- | --- |
| ADD (junk token) | 54 of 73 | Token count is not enforced (P-2.2) |
| DROP (last token) | 43 of 72 | A payload token is optional (P-2.1, P-2.2) |
| DEL (row) | 34 of 73 | The row is optional or defaulted (P-2.1) |
| DUP (row) | 37 of 73 | Duplicates pass silently (P-2.3) |

**Junk token accepted.** Every structural predicate tested except `let`, `set`,
`return`, `instantiates`, and `literalDigest`. That includes `invokes`, `arg`,
`in`, `out`, `catch`, `effect`, `uses`, `grants`, `do`, `branch`, `goto`,
`start`, `join`, `defer`, `entry`, `target`, `field`, and all `storage` facts.
The prose predicates (`purpose`, `invariant`) are the ones that enforce arity.
There is no per-predicate shape table: `ALLOWED_PREDICATES` holds names only.

**Rows that can be deleted** (single-valued facts, so deletion means an implicit
default or a missing check):

| Row | Accepted | Note |
| --- | --- | --- |
| `operation effect` | 12/12 | The effect declaration is not required (LR-07) |
| `operation memory` | 12/12 | Implicit default |
| `operation async` | 11/12 | Implicit default |
| `alias for` | 12/12 | An alias with no target type |
| `project entry`, `target`, `module`, `mode` | all | Implicit defaults |
| `module path` | 12/12 | Implicit default |
| `call in` | 6/12 | Owner inferred from use |
| `cleanup in` | 12/12 | Owner inferred from use |
| `storage mutability`, `storage value` | 12/12 | Implicit defaults (LR-08) |
| `operationType out` | 2/2 | Implicit `Void` |
| `call discards` | 1/12 | An unused result with no stated discard |

Repeatable rows (`enum variant`, `record field`) can also be deleted when the
member is unused. That is a valid program, not an implicit default. Metadata
rows (`purpose`, `invariant`, `risk`) are optional on most kinds; whether prose
is required at all is LR-06.

**Last token can be dropped** (the row keeps its meaning with less stated):

- Typed bindings without the type: `call out NAME`, `task out NAME`,
  `call catch NAME`, `operation in NAME`, `operation let NAME MUT TYPE` with no
  value.
- Bare predicates with no payload at all: `alias for`, `call in`, `cleanup in`,
  `cleanup cleans`, `call cleanedBy`, `call discards`, `module path`,
  `project entry`, `project target`, `project module`, `operation async`,
  `operation cancel`, `operation poll`, `storage mutability`, `storage value`,
  `operationType out`.
- Shortened facts: `operation effect write` (no resource), `operation memory
  heap` (no yes/no), `record field NAME` (no type), `enum variant` (no name).

**Duplicate rows accepted** (declarations only; repeating a step row is a
different program, not a duplicate):

- Single-valued: `call invokes`, `call in`, `task invokes`, `task in`,
  `cleanup in`, `operation body`, `call catch`, `project target`,
  `project mode`, `storage literalSource`.
- Same member twice: `call arg` and `task arg` (same parameter bound twice),
  `operation in`, `operation typeParam`, `operation effect`, `operation uses`,
  `capability grants`, `module exports`, `project module`, `call owns`.

### What already holds

- These rows are required today: `call invokes`, `call arg`, `call out`,
  `call catch`, `capability grants`, `module exports`, `operation in`,
  `operation out`, `operation uses`, `storage scope`, `storage type`,
  `task in`, `task invokes`, and the `purpose`/`invariant` pair on modules.
- Duplicates are already rejected for `let`, `out`, `async`, `memory`,
  `entry`, `alias for`, `storage scope/type/mutability/value`, and
  `record field`.

## Enforcement plan (draft)

Ordered so each step is small, testable, and does not depend on a later one.

1. **Predicate shape table.** Includes the LR-18 skeletons: required header
   predicates per kind, `none` for empty sets, `input`/`output` on operations,
   and a reserved-word list of literals only. One table keyed by (kind, predicate) giving the
   exact token count or range, a token class or closed value set per position,
   and cardinality (`one`, `optional`, `many`). The parser enforces it. This
   closes ADD and DROP in one place and replaces `ALLOWED_PREDICATES`. The same
   table generates `GRAMMAR.md` and the editor grammar.
2. **Cardinality and duplicates.** From the same table: single-valued facts
   appear exactly once; repeatable facts reject identical repeats and repeated
   keys (same `arg` parameter, same `in` name). Closes DUP.
3. **Required rows, no defaults.** Mark as required every row the DEL table
   lists: `effect` (when any activated target has effects, LR-07), `memory`,
   `async`, `alias for`, `project entry/target/module`, `module path`,
   `call in`, `cleanup in`, `storage mutability/value`, `operationType out`,
   and a `catch` or `discards` row on every fallible call. Closes DEL.
4. **Checked statements.** The lexical rules from LR-11 and the conversion and
   shift traps from LR-12 land here too. Restated facts are verified: `arg` type against the
   binding and the parameter (LR-05), `out`/`catch` types against the target's
   signature, `in` owner against the activating operation, `uses` against a
   declared capability (LR-07).
5. **Flow checks (LR-04, LR-16, LR-18, LR-22, LR-23).** Loops are declared
   with a kind and stated membership; each kind's shape is checked. Loop bounds and recursion
   depth are stated and enforced at run time; `useRetry` is removed. Every step row carries its block
   label; branches name both targets; loop bounds attach to blocks. Build a control-flow graph per operation and
   enforce definite assignment, a `return` on every path, and the return type
   against `out`. Run LLVM's verifier inside `check` as a backstop.
6. **Scoped names (LR-02).** Resolve call, task, cleanup, label, and binding
   names per operation.
7. **One spelling (LR-14, LR-15).** Ship the one-time migration command, then
   reject the compact profile and every sugar form.
8. **Memory and ownership (LR-20).** Region entities with stated lifetimes;
   `ownedBy` on every call; passing modes on every `input` and `arg`; the
   per-path linear check for operation-owned values; exact `memory heap`
   check; raw allocation rejected in application source. Port the standard
   library to region-taking operations.
9. **Context rows and comments (LR-06, LR-21).** Closed set of context
   predicates; typed-comment grammar removed; `fmt` keeps every comment
   attached to its row. Remove SS1880. Require `purpose` and `invariant` on
   product-meaning entities only. Add invariant ids and the rule that each is
   referenced by a test. Add the filler check and the staleness flag.
10. **Migrate the corpus.** Run the formatter or a one-time fixer to add the rows
    steps 3, 8, and 9 make mandatory, across `examples/`, `apps/`, and `std/`.
11. **Make the audit a gate.** Run `tests/audit/row_mutation_audit.py` in CI and
   fail on any accepted ADD, DROP, or DUP, and on any accepted DEL of a required
   row. Add strict-clean examples for the ten uncovered kinds so the gate sees
   them.

12. **Agent-writability evaluation (LR-18).** A small and a large model write a
    fixed set of programs from the spec alone. Track the first-try
    `check --strict` pass rate and which rules are broken, and feed the results
    back into this file.

No open question blocks step 1. Part 2 adds two steps, which come after the
enforcement steps because they build on the checked core:

13. **Language completion (LR-24 to LR-39).** Generics by instantiation,
    collections and `forEach`, tables, text and bytes, `unset` merge
    variables, `raises` and `return ok|error`, the four passing modes, the
    single import form, task groups and deadlines, tests.
14. **Standard library (LR-40).** Rewrite the library to the contract, then
    make `docs/refined-examples/` compile and run. Those two files are the
    acceptance test for this plan.

## Decision log

| Date | Item | Decision |
| --- | --- | --- |
| 2026-11-13 | P-1 | Source is verbose and 100% explicit; agents are the authors |
| 2026-11-13 | P-2 | Explicit construction is enforced: no defaults, fixed shapes, no silent duplicates, no unchecked statements |
| 2026-11-13 | LR-03 | Dropped; row count is not a problem under P-1 |
| 2026-11-13 | LR-05 | Keep the type on `arg` rows and check it |
| 2026-11-13 | LR-08 | `mutability` is required, closed set `mutable \| immutable`, no default |
| 2026-11-13 | LR-09 | Every predicate gets a fixed shape, enforced from one table |
| 2026-11-13 | LR-06 | `purpose` and `invariant` stay as rows on product-meaning entities; `purpose` is unchecked intent; each `invariant` has an id referenced by a test; staleness flag; no filler; SS1880 removed |
| 2026-11-13 | LR-01 | No inline call form; canonical order puts each call after its operation; `fmt --check` is in the strict gate (by delegation) |
| 2026-11-13 | LR-02 | Call, task, cleanup, label, and binding names are scoped to the owning operation (by delegation) |
| 2026-11-13 | LR-04 | Definite assignment and return-on-every-path are check errors; no loop sugar (by delegation) |
| 2026-11-13 | LR-07 | Targets state effects in signatures; effects are transitive and must be declared and covered; unresolved `uses` is always an error (by delegation) |
| 2026-11-13 | LR-11 | Whitespace is space and tab only; control bytes and misplaced quotes are errors (by delegation) |
| 2026-11-13 | LR-12 | Signed-to-unsigned of a negative value traps; out-of-range shift amounts trap (by delegation) |
| 2026-11-13 | LR-13 | Enforcement plan first, then §34 demotions minus the metadata step (by delegation) |
| 2026-11-13 | LR-14 | Compact profile removed (by delegation) |
| 2026-11-13 | LR-15 | All sugar forms become errors after a one-time migration (by delegation) |
| 2026-11-13 | LR-16 | Steps form an explicit control-flow graph: two-target branches, no fallthrough, bounded loops (by delegation) |
| 2026-11-13 | LR-17 | Owned tasks, cooperative single-thread scheduling, isolated workers for parallelism; task rows rejected until implemented (by delegation) |
| 2026-11-13 | LR-18 | Fixed skeletons with explicit `none`; every step row names its block; `input`/`output`; one boolean spelling; `ifFalse` removed; only literals reserved (by delegation) |
| 2026-11-13 | LR-19 | Each operation frees the ordinary values it made when it returns, unless it returned them; the region is a required row; raw malloc is standard-library only (accepted by owner) |
| 2026-11-13 | All | Owner accepted the refinement as a whole. Decisions marked "by delegation" stand as confirmed. LR-10 remains open |
| 2026-11-13 | LR-20 | Every releasable value has one named owner; regions are declared with a stated lifetime; allocation takes a region argument; every `input` and `arg` states its passing mode; operation-owned values are linear per path; supersedes LR-19 (accepted by owner) |
| 2026-11-13 | LR-21 | Comments stay as free space for authors, untagged, never checked, never moved by `fmt`. Structured context is rows: `purpose`, `invariant`, `rationale`, `risk <category>`, `note`, `todo`, `deprecated`. (Owner overturned the first version, which removed comments) |
| 2026-11-13 | LR-22 | Every loop block states a bound that is enforced at run time; `unbounded` needs a reason; `useRetry` removed in favor of written-out retry loops; recursive operations state `maxRecursion` (accepted by owner) |
| 2026-11-13 | LR-23 | A loop is declared on its header with a kind (`counted`, `while`, `doWhile`, `forEach`, `forever`); member blocks state `within`; single entry; the compiler checks each kind's shape and proves `counted` loops terminate (accepted by owner) |
| 2026-11-13 | LR-10 | Closed: loops are LR-16/22/23, generics LR-24, collections LR-25 (by delegation) |
| 2026-11-13 | LR-24 | Generics only through named instantiations with derived call targets; no inference (by delegation) |
| 2026-11-13 | LR-25 | Generic `List`, `Map`, `Set`, region-owned; fallible reads; `forEach` driven by `branch ifNext ... bind`; typed index aliases with `indexes` (by delegation) |
| 2026-11-13 | LR-26 | `table` entity for constant records, one `cell` fact per row (by delegation) |
| 2026-11-13 | LR-27 | `String`, `Bytes`, `ByteBuffer`; byte offsets; fallible `byteAt` and `slice`; no implicit conversion (by delegation) |
| 2026-11-13 | LR-28 | Immutable records and enums; class follows contents; `Option T` replaces `nil` (by delegation) |
| 2026-11-13 | LR-29 | `let <name> mutable <type> unset` for values set on several paths (by delegation) |
| 2026-11-13 | LR-30 | Errors are enums; every operation states `raises`; `return ok` / `return error`; no propagation shorthand (by delegation) |
| 2026-11-13 | LR-31 | Four passing modes; call skeleton gains `borrows`; `cleanedBy none`; `outputOwner`; built-in `static` region (by delegation) |
| 2026-11-13 | LR-32 | One file one module; one `imports` form; names always carry their module prefix; selective import predicates removed (by delegation) |
| 2026-11-13 | LR-33 | Waiting calls are tasks; every wait takes a `Deadline`; `taskGroup` for many tasks (by delegation) |
| 2026-11-13 | LR-34 | Arguments, streams, `process.run`; every capability states a `scope` (by delegation) |
| 2026-11-13 | LR-35 | Files and sockets as operation-owned resources; file writing and listening sockets added (by delegation) |
| 2026-11-13 | LR-36 | HTTP is a library; `webServer`, `htmlTemplate`, and indentation-based islands removed (by delegation) |
| 2026-11-13 | LR-37 | Operation references keep the full skeleton and declared effects; no closures (by delegation) |
| 2026-11-13 | LR-38 | No implicit numeric conversion; trapping arithmetic by default with named wrapping and saturating targets (by delegation) |
| 2026-11-13 | LR-39 | `test` entity with `verifies <operation> <invariantId>` (by delegation) |
| 2026-11-13 | LR-40 | Standard library contract and the module list the two targets need (by delegation) |
| 2026-11-13 | LR-41 | Known gaps recorded: float formatting, JSON, TLS, sorting and hashing, worker pools (by delegation) |
| 2026-11-13 | LR-42 | 26 amendments after an adversarial review, including: `arg none`; `maxIterations` counts returns to the header; imported types and variants are prefixed; `match`/`case` replaces `ifVariant`; every block declares `loopKind` and `within`; `memory stack`/`memory max` removed (reverses part of owner-accepted LR-20); literals only in `let` and `cell` rows (by delegation) |
| 2026-11-13 | Part 4 | Implementation started as a new front end beside the legacy compiler; decisions D-1 to D-15 recorded there (by delegation) |
| 2026-11-13 | Part 5 | No bridge and no backwards compatibility (owner); the refined compiler has its own LLVM backend; every Part 4 open item enforced; decisions D-16 to D-23 (by delegation) |
| 2026-11-13 | Part 6 | Earlier compiler, examples, runtime, vendored C, tests, docs, and CI lanes removed (owner); CI, editor, and docs point at the refined compiler |
| 2026-11-14 | Part 9 | Library, tooling, native output, FFI, and packages; decisions D-33 to D-36 (by delegation) |
| 2026-11-14 | Part 8 | Backend completed so every program compiles and runs; decisions D-27 to D-32 (by delegation; D-31 replaces D-27) |
| 2026-11-14 | Part 7 | Test suite and generated coverage map (owner); fixes for what it found; decisions D-24 to D-26 (by delegation) |
| 2026-11-14 | Part 10 | Adversarial refinement: loan, task, scope, and test holes closed; decisions D-38 to D-41 (by delegation) |
| 2026-11-14 | D-43 to D-47 | Exclusive handle loans, cancel-then-join, table loop bounds, no exported capabilities, a conformance suite; one consistent syntax pattern (owner) |

## Parking lot

Ideas raised but not yet written up as items.

-
